# A Makefile with tab-indented recipes — it passes.

CC = gcc
CFLAGS = -Wall -O2

all: app

app: main.o util.o
	$(CC) $(CFLAGS) -o app main.o util.o

main.o: main.c
	$(CC) $(CFLAGS) -c main.c

clean:
	rm -f app *.o

.PHONY: all clean
