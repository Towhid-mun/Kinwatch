/* Duplex USB-serial chat: forwards stdin -> serial device and
 * serial device -> stdout. Portable POSIX (termios/poll), so the same
 * source builds on both ends of the Mac<->Pi USB gadget link:
 *   Pi:  /dev/ttyGS0            (built and run via perch)
 *   Mac: /dev/cu.usbmodemXXXX   (built and run locally with clang -
 *        this half necessarily runs on the Mac itself, not on the target)
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

static int open_serial(const char *path) {
    int fd = open(path, O_RDWR | O_NOCTTY);
    if (fd < 0) {
        perror(path);
        return -1;
    }

    struct termios tio;
    if (tcgetattr(fd, &tio) < 0) {
        perror("tcgetattr");
        close(fd);
        return -1;
    }
    cfmakeraw(&tio);
    cfsetispeed(&tio, B115200);
    cfsetospeed(&tio, B115200);
    tio.c_cflag &= ~CRTSCTS; /* no hardware flow control on a gadget-serial link */
    tio.c_cflag |= CLOCAL;
    if (tcsetattr(fd, TCSANOW, &tio) < 0) {
        perror("tcsetattr");
        close(fd);
        return -1;
    }

    /* macOS's USB-CDC-ACM driver needs a moment to apply the termios
     * change (baud rate especially) over its USB control transfer before
     * the bulk OUT endpoint reliably accepts writes - a write issued
     * immediately after open/reconfigure here is silently dropped. */
    usleep(2000000);

    return fd;
}

static int pump(int from_fd, int to_fd) {
    char buf[4096];
    ssize_t n = read(from_fd, buf, sizeof buf);
    if (n < 0) {
        if (errno == EINTR)
            return 0;
        perror("read");
        return -1;
    }
    if (n == 0)
        return -1; /* EOF */

    ssize_t off = 0;
    while (off < n) {
        ssize_t w = write(to_fd, buf + off, n - off);
        if (w < 0) {
            if (errno == EINTR)
                continue;
            perror("write");
            return -1;
        }
        off += w;
    }
    return 0;
}

/* Like pump(STDIN_FILENO, serial_fd), but a typed "quit" line ends the
 * session locally instead of being sent to the peer. Relies on stdin
 * being in canonical mode (the default here), so one read() = one typed
 * line. */
static int handle_stdin(int serial_fd) {
    char buf[4096];
    ssize_t n = read(STDIN_FILENO, buf, sizeof buf);
    if (n < 0) {
        if (errno == EINTR)
            return 0;
        perror("read");
        return -1;
    }
    if (n == 0)
        return -1; /* EOF */

    /* Trim trailing \r and/or \n before comparing - a remote pty (e.g.
     * over `perch run --tty`) doesn't always deliver the same line
     * ending a local terminal would. */
    ssize_t trimmed = n;
    while (trimmed > 0 && (buf[trimmed - 1] == '\n' || buf[trimmed - 1] == '\r'))
        trimmed--;
    if (trimmed == 4 && memcmp(buf, "quit", 4) == 0)
        return -1;

    ssize_t off = 0;
    while (off < n) {
        ssize_t w = write(serial_fd, buf + off, n - off);
        if (w < 0) {
            if (errno == EINTR)
                continue;
            perror("write");
            return -1;
        }
        off += w;
    }
    return 0;
}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "/dev/ttyGS0";

    int serial_fd = open_serial(path);
    if (serial_fd < 0)
        return 1;

    fprintf(stderr, "listening on %s - type a line and press enter to send, or \"quit\" to exit\n", path);

    struct pollfd fds[2] = {
        {.fd = STDIN_FILENO, .events = POLLIN},
        {.fd = serial_fd, .events = POLLIN},
    };

    for (;;) {
        int ready = poll(fds, 2, -1);
        if (ready < 0) {
            if (errno == EINTR)
                continue;
            perror("poll");
            break;
        }
        if (fds[0].revents & POLLIN) {
            if (handle_stdin(serial_fd) < 0)
                break;
        }
        if (fds[1].revents & POLLIN) {
            if (pump(serial_fd, STDOUT_FILENO) < 0)
                break;
        }
    }

    close(serial_fd);
    return 0;
}
