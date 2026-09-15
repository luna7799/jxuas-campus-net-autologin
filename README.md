# 江西应用科技学院校园网自动连接与认证工具（JXUAS AutoLogin）

一个面向江西应用科技学院师生的开源小工具：自动连接校园网 WiFi（`JXUAS`），并调用本机 **Microsoft Edge** 浏览器自动完成校园网网页认证门户的登录，让你回到校园/宿舍时免去手动输入学号密码的重复劳动。

> 认证流程严格依据校方微信公众号《@新同学，这份校园生活指南，请查收！》中的「校园网连接教程」还原：
>
> - 无线信号：`JXUAS`（宿舍信号偏弱可切换 `JXUAS-2.4G`）
> - 认证门户：`http://172.16.20.18/`
> - 用户名：学号；初始密码：身份证后 6 位（**首次登录强制修改密码**）
> - 接入选项：`校园网学生接入`
> - 自助服务平台：`http://172.16.20.19:8080/selfservice/`（运营商宽带绑定）

## 特性

- **自动认证**：检测到网络未认证时，自动拉起 Edge 填写账号/密码、选中接入选项并点击登录。
- **自动连 WiFi**：支持在已保存过密码的前提下，自动切换到 `JXUAS` 校园网信号。
- **常驻守护**：循环检测网络状态，掉线自动重连、自动重新认证。
- **开机自启动**：一键写入注册表（当前用户，无需管理员权限），开机即用。
- **可配置**：账号、密码、WiFi 名、接入选项、检测间隔等均可通过 JSON 配置修改。
- **可打包**：一键打包为独立 `.exe`，双击即可运行。
- **中文注释**：核心逻辑均含详细中文注释，便于二次开发。

## 目录结构

```
jxuas-campus-net-autologin/
├── README.md                     # 本文件
├── LICENSE                       # MIT 开源协议
├── requirements.txt              # Python 依赖清单
├── build.bat                     # 一键打包为 .exe 的脚本
├── run.bat                       # 直接运行源码的便捷脚本
├── .gitignore
├── .gitattributes
├── config/                       # 配置目录
│   ├── config.json               # 实际生效的配置（填写你的账号密码）
│   └── config.example.json       # 配置示例（带字段说明）
├── src/                          # 脚本源码目录
│   ├── __init__.py
│   ├── main.py                   # 主入口：命令行参数 + 常驻循环
│   ├── config.py                 # 配置加载/生成
│   ├── logger.py                 # 日志（控制台 + 文件）
│   ├── network.py                # 网络检测 + WiFi 连接
│   ├── authenticator.py          # 核心：Edge 自动认证
│   └── autostart.py              # 开机自启动（注册表）
├── scripts/                      # 辅助脚本目录
│   ├── install_autostart.bat     # 安装开机自启动
│   └── uninstall_autostart.bat   # 取消开机自启动
└── docs/                         # 文档目录
    ├── 环境准备.md
    ├── 安装部署.md
    ├── 配置修改.md
    └── 日常使用.md
```

## 快速开始

### 方式一：源码运行（推荐二次开发）

1. 安装 [Python 3.8+](https://www.python.org/downloads/)（安装时勾选 **Add Python to PATH**）。
2. 克隆仓库并安装依赖：

   ```bash
   git clone https://github.com/<你的用户名>/jxuas-campus-net-autologin.git
   cd jxuas-campus-net-autologin
   pip install -r requirements.txt
   ```

3. 编辑 `config/config.json`，填入你的学号与密码：

   ```json
   "account": {
     "username": "你的学号",
     "password": "你的密码",
     "access_option": "校园网学生接入"
   }
   ```

4. 运行：

   ```bash
   python src/main.py
   ```

   双击 `run.bat` 也可达到同样效果。

### 方式二：打包为 .exe（推荐日常使用）

1. 双击运行 `build.bat`，脚本会自动创建虚拟环境、安装依赖并打包。
2. 打包完成后得到 `dist/jxuas-autologin.exe`，双击即可运行（首次运行会自动下载与 Edge 匹配的 WebDriver）。
3. 配置文件位于 `dist/config/config.json`，按需填写账号密码。

## 开机自启动

- **已打包**：双击 `scripts/install_autostart.bat`。
- **源码运行**：`python src/main.py --install-autostart`。

取消自启动：双击 `scripts/uninstall_autostart.bat` 或 `python src/main.py --uninstall-autostart`。

> 自启动写入的是**当前用户**的注册表 Run 项（`HKCU\...\Run`），不需要管理员权限，也不会影响其他程序。

## 配置说明

核心配置位于 `config/config.json`，常用字段：

| 字段 | 说明 | 默认值 |
| --- | --- | --- |
| `network.ssid` | 校园网 WiFi 名称 | `JXUAS` |
| `network.ssid_backup` | 备用 WiFi（宿舍信号弱） | `JXUAS-2.4G` |
| `network.portal_url` | 认证门户地址 | `http://172.16.20.18/` |
| `account.username` | 用户名（学号） | 空 |
| `account.password` | 密码 | 空 |
| `account.access_option` | 接入选项 | `校园网学生接入` |
| `browser.headless` | Edge 是否无头运行 | `false` |
| `auto_login.check_interval` | 检测间隔（秒） | `30` |
| `auto_login.max_retry` | 认证失败重试次数 | `3` |

完整的字段说明见 [`docs/配置修改.md`](docs/配置修改.md)。

## 命令行参数

```
python src/main.py [选项]

  --once               仅执行一次检测与认证后退出
  --setup              交互式填写配置（账号/密码/网络名等）
  --config PATH        指定配置文件路径
  --headless           Edge 无头模式（后台运行）
  --install-autostart  注册开机自启动
  --uninstall-autostart 取消开机自启动
```

## 工作原理

1. 周期性访问外网测试地址，判断当前是否已联网/已认证。
2. 若未认证：先尝试连接到 `JXUAS` WiFi，再探测认证门户是否可达。
3. 门户可达时，启动 Edge 打开 `http://172.16.20.18/`，定位用户名/密码输入框、接入选项下拉框与登录按钮并自动填写提交。
4. 认证提交后再次探测外网，确认是否成功；失败则按配置重试。

> 之所以用浏览器自动化而不是直接 POST：认证门户由页面自身的 JavaScript 负责密码加密与会话校验，直接驱动浏览器可天然复用这些逻辑，对门户改版也更具鲁棒性。

## 常见问题

- **首次登录提示修改密码**：首次登录系统强制改密，脚本无法代劳。请先手动登录一次并修改密码，之后即可自动认证。
- **账号不存在/密码异常**：加入网络反馈 QQ 群 `869659135`、`1062385993` 联系管理员。
- **已缴费但账号未开通**：缴费后系统约 24 小时内同步账号。
- **运营商宽带绑定**：需先在自助服务平台 `http://172.16.20.19:8080/selfservice/` 手动绑定一次（账号格式 `手机号@lan`），本工具负责的是校园网认证。
- **首次运行自动下载驱动失败**：Selenium 首次运行需联网下载与 Edge 版本匹配的 `msedgedriver`，请确保机器当时可联网（如先用手机热点、或手动登录一次后再运行）。

更多排查见 [`docs/日常使用.md`](docs/日常使用.md)。

## 发布到 GitHub

本仓库已按规范初始化，可直接推送：

```bash
git remote add origin https://github.com/<你的用户名>/jxuas-campus-net-autologin.git
git branch -M main
git push -u origin main
```

## 免责声明

本项目仅供学习与个人便利使用，请遵守校方网络管理规定，妥善保管个人账号密码，**切勿将包含真实密码的配置提交到公开仓库**。因使用本工具产生的一切后果由使用者自行承担。

## License

[MIT](LICENSE)
