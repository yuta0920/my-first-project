import csv
import os
import datetime
import smtplib
import subprocess
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr


def _ps_escape(s):
    return (s or "").replace("'", "''")


def notify_windows(title, message):
    """Windowsのバルーン通知(トースト)を表示する。失敗しても例外は投げない。"""
    title_e = _ps_escape(title)
    message_e = _ps_escape(message)
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "Add-Type -AssemblyName System.Drawing;"
        "$n = New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon = [System.Drawing.SystemIcons]::Information;"
        "$n.Visible = $true;"
        f"$n.ShowBalloonTip(15000, '{title_e}', '{message_e}', "
        "[System.Windows.Forms.ToolTipIcon]::Info);"
        "Start-Sleep -Seconds 16;"
        "$n.Dispose();"
    )
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        print(f"[通知エラー] {e}")


def _split_recipients(to_addr):
    """to_addr が文字列(カンマ区切り可)でもリストでも、宛先アドレスのリストに正規化する。"""
    if isinstance(to_addr, str):
        candidates = to_addr.split(",")
    else:
        candidates = to_addr
    return [a.strip() for a in candidates if a and a.strip()]


def send_email(subject, body, to_addr, smtp_server, smtp_port, smtp_user, smtp_password):
    """SMTPでメールを送る。設定が足りない場合は送らずFalseを返す(例外は投げない)。
    Gmailを使う場合は smtp_password に『アプリパスワード』を指定すること。
    to_addr はカンマ区切りの文字列(例: "a@x.com,b@y.com")、またはリストで複数宛先を指定できる。
    """
    recipients = _split_recipients(to_addr)
    if not (recipients and smtp_server and smtp_user and smtp_password):
        print("[メール] 送信設定が未入力のためスキップしました")
        return False

    try:
        port = int(smtp_port) if smtp_port else 587
    except ValueError:
        port = 587

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("ベイブレードX 監視ツール", "utf-8")), smtp_user))
    msg["To"] = ", ".join(recipients)

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(smtp_server, port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_server, port, timeout=30)
            server.starttls()
        try:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, recipients, msg.as_string())
        finally:
            server.quit()
        print(f"[メール] {', '.join(recipients)} 宛に送信しました")
        return True
    except Exception as e:
        print(f"[メール] 送信に失敗しました: {e}")
        return False


def log_hit(log_file, site, name, price, in_stock, url):
    exists = os.path.exists(log_file)
    with open(log_file, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp", "site", "name", "price", "in_stock", "url"])
        w.writerow(
            [
                datetime.datetime.now().isoformat(timespec="seconds"),
                site,
                name,
                price,
                in_stock,
                url,
            ]
        )
