#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

int main(void) {
    errno = 0;
    pid_t ppid = getppid();

    if (ppid == -1) {
        printf("getppid blocked: errno=%d (%s)\n", errno, strerror(errno));
        return 1;
    }

    printf("getppid allowed: parent PID=%d\n", ppid);
    return 0;
}
