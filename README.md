# 👨‍🔬 DoraSuper Bot 🤖

Chào mừng bạn đến với **DoraSuper Bot** – một bot Telegram mạnh mẽ và linh hoạt được thiết kế để quản lý nhóm hiệu quả, mang lại trải nghiệm tương tác thú vị và tiện lợi cho cộng đồng của bạn. Được xây dựng trên nền tảng Python 3, Pyrogram và MongoDB, DoraSuper Bot cung cấp khả năng tùy biến cao và hiệu suất đáng tin cậy.

## 🚀 Tính năng chính

  * **Quản lý nhóm toàn diện:** Các lệnh quản trị nhóm cơ bản đến nâng cao.
  * **Tương tác thông minh:** Tùy chỉnh các phản hồi và tương tác của bot.
  * **Tích hợp cơ sở dữ liệu:** Lưu trữ và quản lý dữ liệu người dùng, nhóm một cách bền vững với MongoDB.
  * **Vô vàn chức năng khác:** Nhiều chức năng đặc biệt được tạo ra với nhiều mục đích khác nhau.
  * **Mở rộng dễ dàng:** Kiến trúc mô-đun cho phép bạn dễ dàng thêm các tính năng mới.

Bot đã dừng phát triển, các lỗi sẽ không được hỗ trợ vui lòng tự kiểm tra và sửa chữa nếu bạn muốn sử dụng.

-----

## 🛠️ Yêu cầu cài đặt

Trước khi bắt đầu, đảm bảo bạn đã cài đặt các công cụ và thư viện cần thiết.

**Python:** Dùng **Python 3.10, 3.11, 3.12 hoặc 3.13** (khuyến nghị **3.13**). Python 3.14 trở lên có thể gặp lỗi với một số thư viện. Nếu gặp lỗi khi `pip install -r requirements.txt`, hãy tạo venv với Python 3.13:

```bash
# Ví dụ: dùng pyenv hoặc python3.13
python3.13 -m venv venv
source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### Hướng dẫn cài đặt trên các Distribution Linux

Mở Terminal và chạy lệnh thích hợp cho hệ điều hành của bạn:

**1. Debian/Ubuntu/Mint:**

```bash
sudo apt update
sudo apt install -y libjpeg-dev zlib1g-dev libwebp-dev python3-pip python3-lxml git wget curl ffmpeg locales tzdata neofetch mediainfo speedtest-cli
```

**2. Fedora/CentOS/RHEL:**

```bash
sudo dnf install -y libjpeg-turbo-devel zlib-devel libwebp-devel python3-pip python3-lxml git wget curl ffmpeg locales tzdata neofetch mediainfo speedtest-cli
```

**3. Arch Linux/Manjaro:**

```bash
sudo pacman -Syu
sudo pacman -S --noconfirm libjpeg-turbo zlib libwebp python-pip python-lxml git wget curl ffmpeg locales tzdata neofetch mediainfo speedtest-cli
```

### Clone dự án

Đầu tiên, bạn cần clone dự án từ kho lưu trữ Git:

```bash
git clone https://git.dabeecao.org/dabeecao/dorasuper-bot.git
cd dorasuper-bot
```

-----

## ⚙️ Cấu hình cơ bản

DoraSuper Bot sử dụng các biến môi trường để cấu hình. Bạn cần tạo một file `config.env` từ `config.env.example` và điền thông tin của bạn.

1.  **Sao chép file cấu hình mẫu:**

    ```bash
    cp config.env.example config.env
    ```

2.  **Mở file `config.env` và điền các giá trị cần thiết:**

    ```ini
    # ==================== Required Vars ====================
    # API_HASH: API Hash của tài khoản Telegram của bạn (lấy từ my.telegram.org)
    API_HASH=

    # API_ID: API ID của tài khoản Telegram của bạn (lấy từ my.telegram.org)
    API_ID=

    # BOT_TOKEN: Token của Bot bạn tạo từ BotFather
    BOT_TOKEN=

    # DATABASE_URI: Chuỗi kết nối MongoDB (ví dụ: mongodb+srv://user:pass@cluster.mongodb.net/dbname)
    DATABASE_URI=

    # LOG_CHANNEL: ID của kênh hoặc nhóm dùng để gửi log và thông báo của bot (ví dụ: -1001234567890)
    LOG_CHANNEL=

    # ==================== Optional Vars ====================
    # SUDO: ID người dùng của các tài khoản Sudo (admin bot), cách nhau bằng dấu cách (ví dụ: 123456789 987654321)
    SUDO=

    # DATABASE_NAME: Tên cơ sở dữ liệu MongoDB (mặc định là 'teobot_db')
    DATABASE_NAME=

    # SUPPORT_CHAT: Username của nhóm hỗ trợ bot (ví dụ: YourSupportChat)
    SUPPORT_CHAT=

    # COMMAND_HANDLER: Ký tự tiền tố cho các lệnh của bot (mặc định là '/')
    COMMAND_HANDLER=/

    # USER_SESSION: Chuỗi phiên Pyrogram cho tài khoản người dùng (nếu bot cần tương tác dưới dạng người dùng)
    USER_SESSION=

    # CURRENCY_API: Khóa API cho dịch vụ chuyển đổi tiền tệ (tùy chọn)
    CURRENCY_API=
    ```

    **Lưu ý:**

      * **`API_HASH`** và **`API_ID`**: Bạn có thể lấy chúng từ [my.telegram.org](https://my.telegram.org/).
      * **`BOT_TOKEN`**: Tạo bot mới hoặc lấy token của bot hiện có từ [@BotFather](https://t.me/BotFather).
      * **`DATABASE_URI`**: Để có chuỗi này, bạn cần có một cơ sở dữ liệu MongoDB. Bạn có thể sử dụng các dịch vụ cloud như [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) hoặc tự cài đặt MongoDB trên máy chủ của mình.
      * **`LOG_CHANNEL`**: Đây là ID số của kênh hoặc nhóm. Đảm bảo bot của bạn là quản trị viên trong kênh/nhóm đó để có thể gửi tin nhắn.

-----

## 🏃‍♂️ Chạy bot

Sau khi đã cài đặt các gói cần thiết và cấu hình `config.env`, bạn có thể chạy bot.


### Tạo và kích hoạt môi trường ảo (venv)

Bạn nên sử dụng môi trường ảo để quản lý các thư viện Python một cách độc lập và tránh xung đột với các dự án khác:

```bash
python3 -m venv venv
```

Để kích hoạt môi trường ảo:

```bash
source venv/bin/activate
```

Sau khi kích hoạt, tên môi trường ảo `(venv)` sẽ xuất hiện ở đầu dòng lệnh của bạn, cho biết bạn đang làm việc trong môi trường ảo.

### Cài đặt các thư viện Python

Khi môi trường ảo đã được kích hoạt, hãy cài đặt tất cả các thư viện Python cần thiết từ file `requirements.txt`:

```bash
pip3 install -r requirements.txt
```

### Khởi động bot

Bây giờ bot của bạn đã sẵn sàng để khởi động:

```bash
python3 -m dorasuper
```

Bot của bạn giờ đây đã sẵn sàng hoạt động\!

-----

## 🔧 Lệnh thủ công (dừng / kill bot)

| Mục đích | Lệnh |
|----------|------|
| **Dừng bot từ Telegram** (bot còn phản hồi) | Gửi `/stop` hoặc `!stop` (chỉ SUDO) |
| **Dừng session screen** | `screen -S dorasuper -X quit` |
| **Kill process bot** (khi treo hoặc chạy nền) | `pkill -f "python.*dorasuper"` hoặc `pkill -f "python3 -m dorasuper"` |
| **Kill ép (force)** | `pkill -9 -f "python.*dorasuper"` |
| **Tìm PID rồi kill** | `ps aux \| grep dorasuper` → `kill <PID>` hoặc `kill -9 <PID>` |
| **Gắn vào session screen** | `screen -r dorasuper` (trong session: `Ctrl+C` để dừng) |

**Chạy lại sau khi dừng:**

```bash
# Trong thư mục dự án
source venv/bin/activate
python3 -m dorasuper
# hoặc dùng screen
./screen.sh
```

-----

## 🤝 Đóng góp

 - Thanks To [yasirarism](https://github.com/yasirarism) for misskaty_patch.
 - Thanks To Dan For [Pyrogram Library](https://github.com/pyrogram/pyrogram) as founder of pyrogram.
 - Thanks To TeamDrivecok and SecretGroup TBK in Telegram.
 - Thanks To [The Hamker Cat](https://github.com/TheHamkerCat) For WilliamButcher Code.
 - Thanks To [Team Yukki](https://github.com/TeamYukki) For AFK Bot Code.
 - Thanks To [Wrench](https://github.com/EverythingSuckz) For Some Code.

Dự án này sử dụng nhiều mã nguồn từ nhiều dự án khác nhau và tôi xin cảm ơn tất cả các nhà phát triển đã góp phần làm nên dự án này. Tôi rất xin lỗi nếu nếu có sử dụng mã của bạn mà không ghi tên bạn vì mã quá phân mảnh và tôi không thể biết chính xác mã nguồn nào là của tác giả nào.

-----

## 📜 Giấy phép

DoraSuper Bot được phát hành dưới giấy phép [GNU Affero General Public License v3.0 (AGPL-3.0)](https://www.gnu.org/licenses/agpl-3.0.html). CẢNH BÁO: Nghiêm cấm hành vi bán mã nguồn cho người khác để lấy tiền.

-----
