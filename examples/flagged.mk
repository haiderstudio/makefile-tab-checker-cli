# A Makefile with space-indented recipe lines — it fails.

all: app

app: main.o
    $(CC) -o app main.o

main.o: main.c
	$(CC) -c main.c

clean:
  rm -f app *.o

install: app
	 cp app /usr/local/bin/app
