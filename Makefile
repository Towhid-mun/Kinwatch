CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2

serial_chat: src/serial_chat.c
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -f serial_chat

.PHONY: clean
