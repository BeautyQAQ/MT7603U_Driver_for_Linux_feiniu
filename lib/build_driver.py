#!/usr/bin/python3
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from common import BASE, cmd, kernel_name

def main():
    kernel = kernel_name(sys.argv[1] if len(sys.argv) > 1 else None)
    headers = Path('/lib/modules') / kernel / 'build'
    if not (headers / 'Makefile').is_file():
        raise RuntimeError(f'缺少飞牛内核头文件：{headers}。请安装与 {kernel} 完全一致的飞牛 headers 后重试，不能用通用 Debian headers 替代。')
    dest = BASE / 'build' / kernel
    dest.mkdir(parents=True, exist_ok=True)
    import fcntl
    with (BASE / 'build/.build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Compile in a fresh work directory, never reuse objects from a previous
        # kernel and never mutate the checked-out source or a loaded driver.
        import tempfile
        work = Path(tempfile.mkdtemp(prefix='work-', dir=dest))
        shutil.copytree(BASE / 'driver', work, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git', 'release', '*.o', '*.ko', '*.cmd',
                                                     '*.mod', '*.mod.c', '*.o.d', '.tmp_versions',
                                                     'Module.symvers', 'modules.order'))
        log = dest / 'build.log'
        print(f'编译内核 {kernel}，日志：{log}', flush=True)
        with log.open('w') as out:
            result = subprocess.run(['make', f'KSRC={headers}', 'DARK_MODE=NO', '-j2'], cwd=work,
                                    stdout=out, stderr=subprocess.STDOUT)
        if result.returncode:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-45:]))
            raise RuntimeError('编译失败；没有替换既有驱动，也没有加载模块。日志与工作目录已保留。')
        module = work / 'os/linux/mt7603usta.ko'
        vermagic = cmd(['modinfo', '-F', 'vermagic', module])
        if vermagic.split()[0] != kernel:
            raise RuntimeError('产物 vermagic 与目标内核不同，拒绝发布。')
        tmp = dest / 'mt7603usta.ko.new'
        shutil.copy2(module, tmp)
        metadata = dict(kernel=kernel, vermagic=vermagic,
                        built_at=datetime.datetime.now().astimezone().isoformat(),
                        source_commit=cmd(['git', '-C', BASE / 'driver', 'rev-parse', 'HEAD']),
                        source_diff_sha256=hashlib.sha256(cmd(['git', '-C', BASE / 'driver', 'diff', 'HEAD', '--', '.']).encode()).hexdigest(),
                        sha256=hashlib.sha256(tmp.read_bytes()).hexdigest(), work_directory=str(work))
        tmp.replace(dest / 'mt7603usta.ko')
        (dest / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print(f'编译成功：{dest / "mt7603usta.ko"}\nvermagic: {vermagic}\n尚未加载或设置开机启动。')

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        sys.exit(str(exc))
