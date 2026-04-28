/*
 * PAM Module for FaceLock - Ubuntu/Linux Integration
 * Enables facial recognition authentication for Linux login
 * 
 * Compile: gcc -fPIC -fno-stack-protector -c pam_facelock.c
 *          gcc -shared -o pam_facelock.so pam_facelock.o -lpam
 * 
 * Install: sudo cp pam_facelock.so /lib/x86_64-linux-gnu/security/
 * 
 * Configure: Edit /etc/pam.d/common-auth or /etc/pam.d/gdm
 *           Add: auth sufficient pam_facelock.so
 */

#define PAM_SM_AUTH
#include <security/pam_modules.h>
#include <security/pam_ext.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <signal.h>

#define SOCKET_PATH "/tmp/facelock_daemon.sock"
#define AUTH_TIMEOUT 15
#define MAX_RESPONSE 256

/* Log message to syslog */
static void log_message(pam_handle_t *pamh, int priority, const char *format, ...) {
    va_list args;
    va_start(args, format);
    pam_vsyslog(pamh, priority, format, args);
    va_end(args);
}

/* Get username from PAM handle */
static int get_username(pam_handle_t *pamh, const char **username) {
    int retval = pam_get_user(pamh, username, NULL);
    if (retval != PAM_SUCCESS) {
        log_message(pamh, LOG_ERR, "Failed to get username: %s", pam_strerror(pamh, retval));
        return retval;
    }
    return PAM_SUCCESS;
}

/* Connect to FaceLock daemon via Unix socket */
static int connect_daemon(pam_handle_t *pamh, int *sock) {
    struct sockaddr_un addr;
    
    *sock = socket(AF_UNIX, SOCK_STREAM, 0);
    if (*sock < 0) {
        log_message(pamh, LOG_ERR, "Failed to create socket: %m");
        return PAM_SYSTEM_ERR;
    }
    
    /* Set timeout for socket operations */
    struct timeval tv;
    tv.tv_sec = AUTH_TIMEOUT;
    tv.tv_usec = 0;
    setsockopt(*sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    
    /* Connect to daemon */
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, SOCKET_PATH, sizeof(addr.sun_path) - 1);
    
    if (connect(*sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        log_message(pamh, LOG_NOTICE, "FaceLock daemon unavailable (using password fallback)");
        close(*sock);
        return PAM_AUTHINFO_UNAVAIL;  /* Fall back to password */
    }
    
    return PAM_SUCCESS;
}

/* Send authentication request to daemon and get response */
static int authenticate_face(pam_handle_t *pamh, int sock, const char *username, char *response) {
    char request[256];
    char buffer[MAX_RESPONSE];
    int n;
    
    /* Format: AUTH_REQUEST:<username> */
    snprintf(request, sizeof(request), "AUTH_REQUEST:%s", username);
    
    /* Send request */
    if (send(sock, request, strlen(request) + 1, 0) < 0) {
        log_message(pamh, LOG_ERR, "Failed to send auth request: %m");
        return PAM_SYSTEM_ERR;
    }
    
    /* Wait for response (with timeout) */
    memset(buffer, 0, sizeof(buffer));
    n = recv(sock, buffer, sizeof(buffer) - 1, 0);
    
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) {
            log_message(pamh, LOG_NOTICE, "Face authentication timeout");
            return PAM_AUTHINFO_UNAVAIL;
        } else {
            log_message(pamh, LOG_ERR, "Failed to receive response: %m");
            return PAM_SYSTEM_ERR;
        }
    }
    
    buffer[n] = '\0';
    strncpy(response, buffer, MAX_RESPONSE - 1);
    
    return PAM_SUCCESS;
}

/* Main PAM authentication function */
PAM_EXTERN int pam_sm_authenticate(pam_handle_t *pamh, int flags, 
                                   int argc, const char **argv) {
    const char *username = NULL;
    int sock = -1;
    char response[MAX_RESPONSE] = {0};
    int retval;
    
    /* Get username */
    if (get_username(pamh, &username) != PAM_SUCCESS) {
        return PAM_USER_UNKNOWN;
    }
    
    log_message(pamh, LOG_DEBUG, "Face authentication attempt for user: %s", username);
    
    /* Connect to daemon */
    if (connect_daemon(pamh, &sock) == PAM_AUTHINFO_UNAVAIL) {
        return PAM_AUTHINFO_UNAVAIL;  /* Daemon not available, use fallback */
    }
    
    if (connect_daemon(pamh, &sock) != PAM_SUCCESS) {
        return PAM_SYSTEM_ERR;
    }
    
    /* Authenticate via face recognition */
    retval = authenticate_face(pamh, sock, username, response);
    
    if (sock >= 0) {
        close(sock);
    }
    
    if (retval != PAM_SUCCESS) {
        return retval;
    }
    
    /* Parse response */
    if (strncmp(response, "AUTH_SUCCESS:", 13) == 0) {
        const char *auth_user = response + 13;
        if (strcmp(auth_user, username) == 0) {
            log_message(pamh, LOG_INFO, "Face authentication successful for user: %s", username);
            return PAM_SUCCESS;
        } else {
            log_message(pamh, LOG_NOTICE, "Face authentication user mismatch: %s vs %s", 
                       auth_user, username);
            return PAM_AUTH_ERR;
        }
    } else if (strncmp(response, "AUTH_FAILED", 11) == 0) {
        log_message(pamh, LOG_NOTICE, "Face authentication failed for user: %s", username);
        return PAM_AUTH_ERR;
    } else {
        log_message(pamh, LOG_ERR, "Invalid response from daemon: %s", response);
        return PAM_AUTHINFO_UNAVAIL;
    }
}

/* Called on session end (cleanup) */
PAM_EXTERN int pam_sm_setcred(pam_handle_t *pamh, int flags, 
                              int argc, const char **argv) {
    return PAM_SUCCESS;
}

/* Module info */
#ifdef PAM_STATIC

struct pam_module _pam_facelock_modstruct = {
    "pam_facelock",
    pam_sm_authenticate,
    pam_sm_setcred,
    NULL,  /* pam_sm_acct_mgmt */
    NULL,  /* pam_sm_open_session */
    NULL,  /* pam_sm_close_session */
    NULL   /* pam_sm_chauthtok */
};

#endif
