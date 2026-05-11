//go:build !windows

package tools

import "syscall"

func getDiskStats(path string) (total, used, avail uint64, files, ffree uint64, err error) {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return 0, 0, 0, 0, 0, err
	}

	blockSize := uint64(stat.Bsize)
	total = stat.Blocks * blockSize
	free := stat.Bfree * blockSize
	avail = stat.Bavail * blockSize
	used = total - free

	return total, used, avail, stat.Files, stat.Ffree, nil
}
