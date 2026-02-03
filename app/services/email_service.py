import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import SITE_URL, SMTP_FROM, SMTP_PASSWORD, SMTP_USER

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.naver.com"
SMTP_PORT = 587


def send_temp_password_email(to_email: str, temp_password: str) -> bool:
    """Send temporary password via Naver SMTP. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP credentials not configured")
        return False

    sender = SMTP_FROM or SMTP_USER
    login_url = f"{SITE_URL.rstrip('/')}/login.html"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[경리 도우미] 임시 비밀번호 안내"
    msg["From"] = sender
    msg["To"] = to_email

    html_body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#f5f5f5">
  <div style="max-width:520px;margin:40px auto;background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.08);overflow:hidden">
    <div style="background:#4F46E5;padding:28px 32px;text-align:center">
      <h1 style="margin:0;color:#fff;font-size:20px;font-weight:700">경리 도우미</h1>
    </div>
    <div style="padding:32px">
      <p style="margin:0 0 16px;color:#333;font-size:15px;line-height:1.6">
        안녕하세요,<br>
        요청하신 임시 비밀번호를 안내드립니다.
      </p>
      <div style="background:#F3F4F6;border-radius:8px;padding:20px;text-align:center;margin:20px 0">
        <p style="margin:0 0 8px;color:#6B7280;font-size:13px">임시 비밀번호</p>
        <p style="margin:0;color:#1F2937;font-size:24px;font-weight:700;letter-spacing:2px">{temp_password}</p>
      </div>
      <p style="margin:16px 0;color:#6B7280;font-size:13px;line-height:1.5">
        보안을 위해 로그인 후 반드시 비밀번호를 변경해 주세요.
      </p>
      <div style="text-align:center;margin:28px 0 12px">
        <a href="{login_url}" style="display:inline-block;background:#4F46E5;color:#fff;text-decoration:none;padding:12px 32px;border-radius:8px;font-size:15px;font-weight:600">
          로그인하러 가기
        </a>
      </div>
    </div>
    <div style="background:#F9FAFB;padding:16px 32px;text-align:center;border-top:1px solid #E5E7EB">
      <p style="margin:0;color:#9CA3AF;font-size:12px">본 메일은 발신 전용입니다.</p>
    </div>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(sender, [to_email], msg.as_string())
        logger.info("Temp password email sent to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False
