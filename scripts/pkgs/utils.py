#!/usr/bin/env python2
# vim:fileencoding=utf-8
# License: GPLv3 Copyright: 2016, Kovid Goyal <kovid at kovidgoyal.net>

from __future__ import (unicode_literals, division, absolute_import,
                        print_function)
import os
import shlex
import pipes
import subprocess
import sys
import errno
import glob
import shutil
import tarfile
import zipfile
from tempfile import mkdtemp

from .constants import PREFIX, SCRIPTS, build_dir, current_source


class ModifiedEnv(object):

    def __init__(self, **kwargs):
        self.mods = kwargs

    def apply(self, mods):
        for k, val in mods.iteritems():
            if val:
                os.environ[k] = val
            else:
                os.environ.pop(k, None)

    def __enter__(self):
        self.orig = {k: os.environ.get(k) for k in self.mods}
        self.apply(self.mods)

    def __exit__(self, *args):
        self.apply(self.orig)


def run_shell():
    return subprocess.Popen(['/bin/bash']).wait()


def run(*args, **kw):
    if len(args) == 1 and isinstance(args[0], type('')):
        cmd = shlex.split(args[0])
    else:
        cmd = args
    env = os.environ.copy()
    if kw.get('library_path'):
        val = kw.get('library_path')
        if val is True:
            val = PREFIX + '/lib'
        else:
            val = val + os.pathsep + PREFIX + '/lib'
        cmd = [SCRIPTS + '/ld.sh'] + cmd
        env['LLP'] = val
    print(' '.join(pipes.quote(x) for x in cmd))
    try:
        p = subprocess.Popen(cmd, env=env)
    except EnvironmentError as err:
        if err.errno == errno.ENOENT:
            raise SystemExit('Could not find the program: %s' % cmd[0])
        raise
    sys.stdout.flush()
    if p.wait() != 0:
        print('The following command failed, with return code:', p.wait(),
              file=sys.stderr)
        print(' '.join(pipes.quote(x) for x in cmd))
        print('Dropping you into a shell')
        sys.stdout.flush()
        run_shell()
        raise SystemExit(1)


def extract(source):
    if source.lower().endswith('.zip'):
        with zipfile.ZipFile(source) as zf:
            zf.extractall()
    else:
        run('tar', 'xf', source)


def extract_source():
    source = current_source()
    tdir = mkdtemp(prefix=os.path.basename(source).split('-')[0] + '-')
    os.chdir(tdir)
    extract(source)
    x = os.listdir('.')
    if len(x) == 1:
        os.chdir(x[0])


def simple_build():
    run('./configure', '--prefix=' + build_dir())
    run('make')
    run('make install')


def lcopy(src, dst):
    try:
        if os.path.islink(src):
            linkto = os.readlink(src)
            os.symlink(linkto, dst)
            return True
        else:
            shutil.copy(src, dst)
            return False
    except EnvironmentError as err:
        if err.errno == errno.EEXIST:
            os.unlink(dst)
            return lcopy(src, dst)


def install_binaries(pattern, destdir='lib'):
    dest = os.path.join(build_dir(), destdir)
    files = glob.glob(pattern)
    for f in files:
        dst = os.path.join(dest, os.path.basename(f))
        islink = lcopy(f, dst)
        if not islink:
            os.chmod(dst, 0o755)


def install_tree(src, dest_parent='include'):
    dest_parent = os.path.join(build_dir(), dest_parent)
    dst = os.path.join(dest_parent, os.path.basename(src))
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)


def ensure_dir(path):
    try:
        os.makedirs(path)
    except EnvironmentError as err:
        if err.errno != errno.EEXIST:
            raise


def create_package(module, src_dir, outfile):

    exclude = frozenset('doc man info'.split())

    def filter_tar(tar_info):
        parts = tar_info.name.split('/')
        for p in parts:
            if p in exclude:
                return
        if hasattr(module, 'filter_pkg') and module.filter_pkg(parts):
            return
        tar_info.uid, tar_info.gid = 1000, 100
        return tar_info

    with tarfile.open(outfile, 'w:bz2') as archive:
        for x in os.listdir(src_dir):
            path = os.path.join(src_dir, x)
            if os.path.isdir(path):
                archive.add(path, arcname=x, filter=filter_tar)


def install_package(pkg_path, dest_dir):
    with tarfile.open(pkg_path) as archive:
        archive.extractall(dest_dir)
