import os
import re
import sys
import time

from flask import Flask, render_template
from flask_socketio import SocketIO

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_rolmer_2026'

# Configuración de SocketIO usando gevent
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')


def emitir_log(mensaje):
    """Envía registros tanto a la consola de Render como al cuadro negro en la web por WebSockets."""
    print(f"LOG: {mensaje}", flush=True)
    socketio.emit('log_event', {'data': mensaje})


def crear_driver():
    """Inicia Chromium + ChromeDriver dentro de Render."""

    emitir_log("Configurando Chromium para Render...")

    options = webdriver.ChromeOptions()

    # Chromium instalado por Docker
    options.binary_location = "/usr/bin/chromium"

    # Navegador invisible
    options.add_argument("--headless=new")

    # Necesarios para Docker / Render
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")

    # Reducir consumo de Chromium
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-default-apps")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-features=Translate,MediaRouter")
    options.add_argument("--window-size=1365,768")

    prefs = {
        "profile.default_content_setting_values.notifications": 2,
    }

    options.add_experimental_option("prefs", prefs)

    # Selenium puede continuar sin esperar todos los recursos secundarios.
    options.page_load_strategy = "eager"

    emitir_log("Usando Chromium: /usr/bin/chromium")
    emitir_log("Usando ChromeDriver: /usr/bin/chromedriver")
    emitir_log("Intentando iniciar Chromium...")

    service = Service(
        executable_path="/usr/bin/chromedriver"
    )

    driver = webdriver.Chrome(
        service=service,
        options=options
    )

    emitir_log("Chromium iniciado correctamente.")

    return driver


def ejecutar_automatizacion(correo, byom_id):
    """Proceso de automatización de Microsoft Outlook y Byom.de."""
    id_simple_byom = byom_id.split("@")[0].strip()
    correo_byom_completo = f"{id_simple_byom}@byom.de"

    emitir_log("=== INICIANDO AUTOMATIZACIÓN EN EL SERVIDOR ===")

    driver = None
    try:
        emitir_log("Iniciando navegador Chrome sin interfaz gráfica...")
        driver = crear_driver()
        wait = WebDriverWait(driver, 20)

        # -------------------------------------------------------------
        # PASO 1: Login Microsoft / Outlook
        # -------------------------------------------------------------
        emitir_log("Paso 1: Abriendo portal de inicio de sesión de Microsoft...")
        driver.get("https://login.live.com/")
        pestana_outlook = driver.current_window_handle

        campo_email = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[type='email'], input[name='loginfmt']")
            )
        )
        campo_email.clear()
        campo_email.send_keys(correo)
        time.sleep(0.5)
        campo_email.send_keys(Keys.ENTER)

        # -------------------------------------------------------------
        # PASO 2: Consultar Byom.de en nueva pestaña
        # -------------------------------------------------------------
        emitir_log("Paso 2: Abriendo Byom.de en nueva pestaña...")
        driver.switch_to.new_window("tab")
        pestana_byom = driver.current_window_handle
        driver.get("https://www.byom.de/")

        campo_busqueda = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[name='cx'], input[type='text'], #target")
            )
        )
        campo_busqueda.clear()
        campo_busqueda.send_keys(id_simple_byom)
        time.sleep(0.5)
        campo_busqueda.send_keys(Keys.ENTER)

        # -------------------------------------------------------------
        # PASO 3: Solicitar el código de recuperación en Outlook
        # -------------------------------------------------------------
        emitir_log("Paso 3: Solicitando envío de código de verificación...")
        driver.switch_to.window(pestana_outlook)
        time.sleep(1.5)

        try:
            casilla_activa = driver.switch_to.active_element
            casilla_activa.send_keys(correo_byom_completo)
            time.sleep(0.5)
            casilla_activa.send_keys(Keys.ENTER)
        except Exception:
            pass

        time.sleep(1)
        try:
            btn_send = driver.find_element(
                By.XPATH,
                "//input[@id='iSignupAction'] | //input[@type='submit'] | //button[contains(.,'Enviar código')]",
            )
            driver.execute_script("arguments[0].click();", btn_send)
        except Exception:
            pass

        # -------------------------------------------------------------
        # PASO 4: Extraer código de verificación en Byom.de
        # -------------------------------------------------------------
        emitir_log("Paso 4: Esperando recepción de correo en Byom.de...")
        driver.switch_to.window(pestana_byom)
        correo_encontrado = False

        for intento in range(30):
            try:
                correo_ms = driver.find_element(
                    By.XPATH,
                    "//td[contains(.,'Microsoft account team') or contains(.,'Your single-use code') or contains(.,'Microsoft')]",
                )
                if correo_ms.is_displayed():
                    correo_encontrado = True
                    time.sleep(3)
                    correo_ms.click()
                    break
            except Exception:
                pass
            time.sleep(2)

        if not correo_encontrado:
            emitir_log("ERROR: No se recibió el correo de verificación a tiempo.")
            return

        try:
            btn_text = driver.find_element(
                By.XPATH, "//a[contains(.,'Text')] | //button[contains(.,'Text')]"
            )
            driver.execute_script("arguments[0].click();", btn_text)
        except Exception:
            pass

        time.sleep(1.5)
        texto_pantalla = driver.find_element(By.TAG_NAME, "body").text
        match = re.search(r":\s*(\d{6,7})\b", texto_pantalla) or re.search(
            r"code\s*is:\s*(\d{6,7})", texto_pantalla, re.IGNORECASE
        )

        if not match:
            emitir_log("ERROR: No se pudo extraer el código del contenido del correo.")
            return

        codigo = match.group(1)
        emitir_log(f"¡CÓDIGO CAPTURADO EXITOSAMENTE!: {codigo}")

        # -------------------------------------------------------------
        # PASO 5: Pegar código en la pestaña de Outlook
        # -------------------------------------------------------------
        emitir_log("Paso 5: Introduciendo código en la sesión de Microsoft...")
        driver.switch_to.window(pestana_outlook)
        time.sleep(1)

        actions = ActionChains(driver)
        actions.send_keys(codigo).perform()
        time.sleep(0.5)
        actions.send_keys(Keys.ENTER).perform()

        # -------------------------------------------------------------
        # PASO 6: Pasar pantallas finales de confirmación
        # -------------------------------------------------------------
        emitir_log("Paso 6: Saltando avisos finales de seguridad...")
        for _ in range(4):
            time.sleep(2)
            try:
                btn_cancel = driver.find_element(
                    By.XPATH,
                    "//button[@id='cancelButton'] | //button[contains(.,'Cancel') or contains(.,'Cancelar')]",
                )
                driver.execute_script("arguments[0].click();", btn_cancel)
            except Exception:
                pass

            try:
                btn_no = driver.find_element(
                    By.XPATH,
                    "//input[@id='idBtn_Back'] | //button[@id='idBtn_Back'] | //button[contains(.,'No')]",
                )
                driver.execute_script("arguments[0].click();", btn_no)
                emitir_log("Omitida pregunta '¿Mantener la sesión iniciada?'")
            except Exception:
                pass
        # -------------------------------------------------------------
        # PASO 7: DEJAR QUE MICROSOFT REDIRIJA POR SU CUENTA
        # -------------------------------------------------------------
                # -------------------------------------------------------------
        # PASO 7: ABRIR OUTLOOK Y MANTENER LA SESION ACTIVA
        # -------------------------------------------------------------
        emitir_log("Paso 7: Abriendo bandeja de entrada de Outlook...")

        driver.get("https://outlook.live.com/mail/0/")

        try:
            WebDriverWait(driver, 60).until(
                lambda d: (
                    "outlook.live.com/mail" in d.current_url.lower()
                    or "outlook.office.com/mail" in d.current_url.lower()
                    or "outlook.com/mail" in d.current_url.lower()
                )
            )

            emitir_log("Outlook Mail abierto correctamente.")

        except Exception:
            emitir_log(
                "ERROR: Outlook no pudo abrir la bandeja de entrada."
            )
            emitir_log(
                "URL actual: " + driver.current_url
            )
            return

        # Avisar a la pagina web
        socketio.emit(
            "outlook_status",
            {
                "ready": True
            }
        )

        emitir_log("OUTLOOK LISTO.")
        emitir_log("Esperando nuevos correos de Amazon...")

        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # MONITOR DE CORREOS DE AMAZON
        # -------------------------------------------------------------

        emitir_log(
            "Monitor de correo iniciado. "
            "Buscando mensajes nuevos de Amazon..."
        )

        amazon_detectado = False

        while True:

            try:
                # Buscar elementos visibles relacionados con el
                # remitente o nombre mostrado por Amazon.
                elementos = driver.find_elements(
                    By.XPATH,
                    "//*[contains("
                    "translate(normalize-space(.),"
                    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                    "'abcdefghijklmnopqrstuvwxyz'),"
                    "'amazon.com'"
                    ")]"
                )

                encontrado = False

                for elemento in elementos:

                    try:
                        texto = elemento.text.strip().lower()

                        if not texto:
                            continue

                        # Nos interesa identificar el mensaje,
                        # no leer códigos de autenticación.
                        if (
                            "amazon.com" in texto
                            or "account-update@amazon.com" in texto
                        ):
                            encontrado = True
                            break

                    except Exception:
                        continue

                if encontrado and not amazon_detectado:

                    amazon_detectado = True

                    emitir_log(
                        "Correo de Amazon detectado en Outlook."
                    )

                    socketio.emit(
                        "amazon_mail_status",
                        {
                            "received": True
                        }
                    )

                    emitir_log(
                        "CORREO DE AMAZON RECIBIDO."
                    )

                elif not encontrado:

                    # Permite detectar nuevamente si desaparece
                    # el mensaje y posteriormente llega otro.
                    amazon_detectado = False

                # Mantener la tarea y el WebSocket activos.
                socketio.sleep(2)

            except Exception as monitor_error:

                emitir_log(
                    "Aviso del monitor de correo: "
                    + str(monitor_error)
                )

                socketio.sleep(3)
                
    except Exception as e:
        emitir_log(f"ERROR DURANTE LA EJECUCIÓN: {str(e)}")

    finally:
        if driver:
            try:
                driver.quit()
                emitir_log("Navegador cerrado correctamente.")
            except Exception:
                pass


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('iniciar_bot')
def handle_iniciar_bot(data):
    correo = data.get('correo', '').strip()
    byom_id = data.get('id_recuperacion', '').strip()

    if not correo or not byom_id:
        emitir_log("ERROR: Debes ingresar tanto el correo como el ID de Byom.")
        return

    emitir_log(f"Recibida solicitud para el correo: {correo}")
    socketio.start_background_task(
        ejecutar_automatizacion,
        correo,
        byom_id
    )


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    socketio.run(
        app,
        host='0.0.0.0',
        port=port
    )   
