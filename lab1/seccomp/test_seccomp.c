#include <seccomp.h>
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>

int main(void) {
    printf("Before seccomp: getppid() = %d\n", (int)syscall(SYS_getppid));
    fflush(stdout);

    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) {
        perror("PR_SET_NO_NEW_PRIVS");
        return 1;
    }

    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ALLOW);
    if (ctx == NULL) {
        perror("seccomp_init");
        return 1;
    }

    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EPERM), SCMP_SYS(getppid), 0) < 0) {
        fprintf(stderr, "Failed to add seccomp rule\n");
        seccomp_release(ctx);
        return 1;
    }

    if (seccomp_load(ctx) < 0) {
        perror("seccomp_load");
        seccomp_release(ctx);
        return 1;
    }

    errno = 0;
    int ppid = (int)syscall(SYS_getppid);
    int saved_errno = errno;
    printf("After seccomp: getppid() = %d, errno = %d (%s)\n",
           ppid, saved_errno, strerror(saved_errno));

    seccomp_release(ctx);
    return (ppid == -1 && errno == EPERM) ? 0 : 2;
}
