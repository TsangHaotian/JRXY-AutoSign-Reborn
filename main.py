"""
今日校园查寝签到工具 - 命令行版
业务逻辑委托给core.CpdailyClient，支持headless模式
"""
import argparse
import sys
import os
from core import CpdailyClient


def main():
    parser = argparse.ArgumentParser(
        prog='python main.py',
        description='今日校园查寝签到工具 - 命令行版',
        epilog='示例:\n'
               '  python main.py login              # 扫码登录\n'
               '  python main.py list               # 列出今日任务\n'
               '  python main.py sign --index 0     # 签到第一个未签任务\n'
               '  python main.py sign --name "晚间"  # 按任务名签到\n'
               '  python main.py --headless list    # 静默查询（使用已保存会话）\n'
               '  python main.py --headless sign --index 0 --photo a.jpg\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--headless', action='store_true',
                        help='静默模式，使用已保存的会话（不弹二维码）')

    sub = parser.add_subparsers(dest='command', required=True)

    # login
    sub.add_parser('login', help='扫码登录')

    # list
    sub.add_parser('list', help='列出今日查寝任务')

    # sign
    sign_p = sub.add_parser('sign', help='签到指定任务')
    sign_p.add_argument('--index', type=int, default=None, help='任务序号（从0开始，对应list输出）')
    sign_p.add_argument('--name', type=str, default=None, help='按任务名匹配')
    sign_p.add_argument('--photo', type=str, default='', help='签到照片路径')

    # status
    sub.add_parser('status', help='检查登录会话状态')

    args = parser.parse_args()

    # 创建客户端
    client = CpdailyClient.from_config()
    client.on_log = lambda msg: print(f'[INFO] {msg}')

    # 初始化学校信息（必须）
    try:
        client.init_school()
    except Exception as e:
        print(f'[ERROR] 初始化失败: {e}')
        sys.exit(1)

    # ===== login =====
    if args.command == 'login':
        if args.headless:
            print('[ERROR] headless模式下无法扫码登录，请先运行 python main.py login')
            sys.exit(1)

        print('[INFO] 正在生成二维码...')
        try:
            uuid, img_bytes = client.get_qr_image()
            qr_file = 'qrcode_login.png'
            with open(qr_file, 'wb') as f:
                f.write(img_bytes)
            print(f'[INFO] 二维码已保存到: {qr_file}')
            print('[INFO] 请用今日校园APP扫描此二维码')
            print('[INFO] 等待扫码...（120秒超时）')

            success = client.poll_qr_login(uuid, on_status=lambda msg: print(f'[INFO] {msg}'))
            if success:
                print('[SUCCESS] 登录成功!')
            else:
                print('[ERROR] 扫码超时或失败')
                sys.exit(1)
        except Exception as e:
            print(f'[ERROR] 登录失败: {e}')
            sys.exit(1)

    # ===== list =====
    elif args.command == 'list':
        if args.headless and not client.logged_in:
            print('[ERROR] 无有效会话，请先运行 python main.py login')
            sys.exit(1)

        try:
            result = client.list_tasks()
        except Exception as e:
            # 会话过期
            if '401' in str(e) or 'unSignedTasks' not in str(e):
                print('[ERROR] 会话已过期，请重新登录: python main.py login')
                sys.exit(1)
            print(f'[ERROR] 获取任务失败: {e}')
            sys.exit(1)

        unsigned = result['unsigned']
        signed = result['signed']

        print(f'\n{"=" * 50}')
        print(f'  今日查寝任务 ({len(unsigned)} 未签 / {len(signed)} 已签)')
        print(f'{"=" * 50}\n')

        if not unsigned and not signed:
            print('  (暂无查寝任务)\n')
            return

        for i, t in enumerate(unsigned):
            tr = f"{t.get('singleTaskBeginTime','')} - {t.get('singleTaskEndTime','')}"
            print(f'  [{i}] ❌ {t["taskName"]}')
            print(f'      {tr}')

        offset = len(unsigned)
        for i, t in enumerate(signed):
            tr = f"{t.get('singleTaskBeginTime','')} - {t.get('singleTaskEndTime','')}"
            print(f'  [{i + offset}] ✅ {t["taskName"]}')
            print(f'      {tr}')

        print()

    # ===== sign =====
    elif args.command == 'sign':
        if args.headless and not client.logged_in:
            print('[ERROR] 无有效会话，请先运行 python main.py login')
            sys.exit(1)

        # 获取任务列表
        try:
            result = client.list_tasks()
        except Exception as e:
            print(f'[ERROR] 获取任务失败: {e}')
            sys.exit(1)

        unsigned = result['unsigned']
        if not unsigned:
            print('[INFO] 没有未签到任务')
            return

        # 确定要签哪个任务
        task = None
        if args.index is not None:
            if args.index < 0 or args.index >= len(unsigned):
                print(f'[ERROR] 序号越界: 0-{len(unsigned) - 1}')
                sys.exit(1)
            task = unsigned[args.index]
        elif args.name:
            for t in unsigned:
                if args.name in t['taskName']:
                    task = t
                    break
            if not task:
                print(f'[ERROR] 未找到名称含"{args.name}"的未签任务')
                sys.exit(1)
        else:
            task = unsigned[0]
            print(f'[INFO] 默认签到第一个未签任务: {task["taskName"]}')

        # 验证照片
        photo_path = args.photo
        if photo_path and not os.path.exists(photo_path):
            print(f'[ERROR] 照片文件不存在: {photo_path}')
            sys.exit(1)

        # 执行签到
        print(f'[INFO] 正在签到: {task["taskName"]}')
        result = client.sign_task(task, photo_path=photo_path)
        if result['success']:
            print(f'[SUCCESS] 签到成功!')
        else:
            print(f'[ERROR] 签到失败: {result["message"]}')
            sys.exit(1)

    # ===== status =====
    elif args.command == 'status':
        if client.logged_in and client.is_session_valid():
            print('[INFO] 登录状态: ✅ 有效')
            print(f'[INFO] 校区: {client.campus}')
        else:
            print('[INFO] 登录状态: ❌ 无效')
            print('[INFO] 请运行 python main.py login 登录')


if __name__ == '__main__':
    main()
