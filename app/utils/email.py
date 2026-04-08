# backend/app/utils/email.py
"""
Envío de emails transaccionales via SMTP.
Usa Gmail SMTP (o cualquier proveedor compatible).

Variables de entorno requeridas:
  SMTP_HOST      → smtp.gmail.com
  SMTP_PORT      → 587
  SMTP_USER      → tu-cuenta@gmail.com
  SMTP_PASSWORD  → contraseña de aplicación de Google (no la personal)
  EMAILS_FROM    → "Siempre de Local <tu-cuenta@gmail.com>"
  FRONTEND_URL   → https://www.siempredelocal.com
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _smtp_config():
    return {
        "host":     os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from":     os.getenv("EMAILS_FROM", "Siempre de Local <no-reply@siempredelocal.com>"),
    }


def send_email(to: str, subject: str, html: str) -> bool:
    """
    Envía un email HTML. Retorna True si fue exitoso, False si falló.
    No lanza excepción para no interrumpir el flujo principal.
    """
    cfg = _smtp_config()
    if not cfg["user"] or not cfg["password"]:
        # Sin credenciales configuradas — no enviar (modo dev sin email)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["from"]
        msg["To"]      = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["user"], [to], msg.as_string())

        return True
    except Exception as e:
        print(f"[email] Error enviando a {to}: {e}")
        return False


def send_password_reset_email(to: str, reset_link: str) -> bool:
    """Email de recuperación de contraseña."""
    frontend_url = os.getenv("FRONTEND_URL", "https://www.siempredelocal.com")

    html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Recuperar contraseña</title>
</head>
<body style="margin:0;padding:0;background:#060d18;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#060d18;padding:40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:520px;background:#0c1625;border-radius:16px;border:1px solid rgba(255,255,255,.08);overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#0d1f3c,#0c1625);padding:32px 40px 24px;text-align:center;border-bottom:1px solid rgba(255,255,255,.06);">
              <img src="{frontend_url}/logo.png" width="80" alt="Siempre de Local"
                   style="display:block;margin:0 auto 16px;" />
              <p style="margin:0;font-size:22px;font-weight:800;color:#e6edf3;letter-spacing:-.3px;">
                Recuperar contraseña
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px 40px;">
              <p style="margin:0 0 16px;font-size:15px;color:#94a3b8;line-height:1.6;">
                Recibimos una solicitud para restablecer la contraseña de tu cuenta en
                <strong style="color:#e6edf3;">Siempre de Local</strong>.
              </p>
              <p style="margin:0 0 28px;font-size:15px;color:#94a3b8;line-height:1.6;">
                Haz clic en el botón para crear una nueva contraseña. Este enlace es válido
                por <strong style="color:#e6edf3;">30 minutos</strong>.
              </p>

              <!-- CTA Button -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center">
                    <a href="{reset_link}"
                       style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#1677ff,#0958d9);color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;border-radius:10px;letter-spacing:.02em;box-shadow:0 8px 24px rgba(22,119,255,.4);">
                      Restablecer contraseña
                    </a>
                  </td>
                </tr>
              </table>

              <p style="margin:28px 0 0;font-size:13px;color:#475569;line-height:1.5;">
                Si no solicitaste este cambio, puedes ignorar este correo. Tu contraseña
                seguirá siendo la misma.
              </p>
              <p style="margin:12px 0 0;font-size:12px;color:#334155;line-height:1.5;word-break:break-all;">
                O copia este enlace en tu navegador:<br/>
                <a href="{reset_link}" style="color:#1677ff;text-decoration:none;">{reset_link}</a>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 40px;border-top:1px solid rgba(255,255,255,.06);text-align:center;">
              <p style="margin:0;font-size:12px;color:#334155;">
                © 2025 Siempre de Local · Chain Reaction Projects S.A.S.<br/>
                Medellín, Colombia
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return send_email(to, "Recupera tu contraseña — Siempre de Local", html)
