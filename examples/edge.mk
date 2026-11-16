# Edge cases: comments, blank lines, variables, define blocks.

CC = gcc

# A comment between a target and its recipe does not end it.
all: app

app: main.o
	$(CC) -o app main.o

# A backslash-continued variable line is one logical line,
# so the space-indented continuation is not a recipe.
FLAGS = -Wall \
    -O2

define GREETING
	echo hello
endef

%.o: %.c
	$(CC) -c $<

.PHONY: all
