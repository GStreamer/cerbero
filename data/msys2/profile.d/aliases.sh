case "$TERM" in
xterm*)
	# The following programs are known to require a Win32 Console
	# for interactive usage, therefore let's launch them through winpty
	# when run inside `mintty`.
	for name in git node ipython php php5 psql python py python3
	do
		alias $name="winpty $name.exe"
	done
	;;
esac
