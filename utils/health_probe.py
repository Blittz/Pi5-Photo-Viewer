"""Read-only health probes, executed in disposable processes off the GUI thread."""
import json
import os
from pathlib import Path
import subprocess
import sys

EXPECTED_PHOTO_MOUNT = Path.home() / 'server' / 'Shared'
BOT_SERVICE = 'discord-bot.service'


def mount_identity(mount):
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields = line.split()
        separator = fields.index('-')
        name = fields[4]
        for escaped, char in [('\\040', ' '), ('\\011', '\t'), ('\\012', '\n'), ('\\134', '\\')]:
            name = name.replace(escaped, char)
        if name == str(mount) and fields[separator + 1] == 'cifs':
            major, minor = map(int, fields[2].split(':'))
            return fields[0], os.makedev(major, minor)
    return None


def check_share(mount, folders):
    mount = Path(os.path.abspath(mount))
    identity = mount_identity(mount)
    if identity is None:
        return False, 'Photo share not mounted'
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(mount, flags)
    try:
        if os.fstat(root_fd).st_dev != identity[1]:
            return False, 'Photo share mount changed'
        # A successful listing is enough: an empty folder is healthy. Do not
        # recursively scan photos, read credentials, create probes, or write files.
        with os.scandir(root_fd) as entries:
            next(entries, None)
        for folder in folders:
            path = Path(os.path.abspath(folder))
            try:
                parts = path.relative_to(mount).parts
            except ValueError:
                continue  # Local and other selected folders are unaffected.
            fd = os.dup(root_fd)
            try:
                for part in parts:
                    child = os.open(part, flags, dir_fd=fd)
                    os.close(fd)
                    fd = child
                if os.fstat(fd).st_dev != identity[1]:
                    return False, 'Photo share mount changed'
                with os.scandir(fd) as entries:
                    next(entries, None)
            finally:
                os.close(fd)
        if mount_identity(mount) != identity:
            return False, 'Photo share mount changed'
        return True, ''
    finally:
        os.close(root_fd)


def check_bot():
    result = subprocess.run(
        ['systemctl', '--system', 'show', BOT_SERVICE, '--property=ActiveState', '--value'],
        capture_output=True, text=True, timeout=3, check=False,
        env={**os.environ, 'SYSTEMD_PAGER': '', 'SYSTEMD_COLORS': '0'})
    if result.returncode:
        return False, 'Photo bot service status unavailable'
    if result.stdout.strip() != 'active':
        return False, 'Photo bot service stopped'
    return True, ''


def main():
    kind = sys.argv[1]
    try:
        if kind == 'share':
            result = check_share(sys.argv[2], sys.argv[3:])
        elif kind == 'bot':
            result = check_bot()
        else:
            raise ValueError('Unknown check')
    except Exception:
        result = (False, 'Photo share unreadable' if kind == 'share'
                  else 'Photo bot service status unavailable')
    print(json.dumps({'ok': result[0], 'message': result[1]}))


if __name__ == '__main__':
    main()
