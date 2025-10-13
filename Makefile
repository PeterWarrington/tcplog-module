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

test-upload:
	curl -s https://raw.githubusercontent.com/sivel/speedtest-cli/master/speedtest.py | python3 - --no-download --single --secure

test-download:
	curl http://ipv4.download.thinkbroadband.com/512MB.zip --output /dev/null