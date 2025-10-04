obj-m += tcplog.o

PWD := $(CURDIR)

all:
	$(MAKE) -C /lib/modules/$(shell uname -r)/build M=$(PWD) modules

clean:
	$(MAKE) -C /lib/modules/$(shell uname -r)/build M=$(PWD) clean

install: uninstall all
	-sudo insmod ./tcplog.ko
	sudo /sbin/sysctl -w net.ipv4.tcp_congestion_control=tcplog

all-install: all install

uninstall:
	-sudo /sbin/sysctl -w net.ipv4.tcp_congestion_control=cubic
	-sudo rmmod tcplog -f