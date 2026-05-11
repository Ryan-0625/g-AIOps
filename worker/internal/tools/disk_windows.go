//go:build windows

package tools

import (
	"golang.org/x/sys/windows"
)

func getDiskStats(path string) (total, used, avail uint64, files, ffree uint64, err error) {
	pathp, err := windows.UTF16PtrFromString(path)
	if err != nil {
		return 0, 0, 0, 0, 0, err
	}

	var freeBytesAvailable, totalNumberOfBytes, totalNumberOfFreeBytes uint64
	if err := windows.GetDiskFreeSpaceEx(pathp, &freeBytesAvailable, &totalNumberOfBytes, &totalNumberOfFreeBytes); err != nil {
		return 0, 0, 0, 0, 0, err
	}

	used = totalNumberOfBytes - totalNumberOfFreeBytes
	return totalNumberOfBytes, used, freeBytesAvailable, 0, 0, nil
}
