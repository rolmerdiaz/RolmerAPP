import os
import re
import sys
import time
import threading
from flask import Flask, render_template
from flask_socketio import SocketIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_rolmer_2026'

# Permite compatibilidad fluida tanto en Windows (threading) como en servidores (eventlet/gevent)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode=None)


def emitir_log(mensaje):
    """Envía registros tanto a la consola del servidor como al cliente web por WebSockets."""
    print(f"LOG: {mensaje}", flush=True)
    socketio.emit('log_message', {'data': mensaje})


def crear_driver():
    """Configura el navegador Chrome adaptándose automáticamente a Windows o Linux/Docker."""
    options = webdriver.ChromeOptions()
    
    # Opciones de estabilidad general
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    
    # Si se ejecuta en servidor Linux / Docker o headless
    if sys.platform != "win32" or os.environ.get("HEADLESS", "false").lower() == "true":
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

    # Selenium 4+ detecta automáticamente ChromeDriver
    driver = webdriver.Chrome(options=options)
    return driver


def ejecutar_automatizacion(correo, byom_id):
    """Proceso completo de automatización entre Outlook y Byom.de."""
    id_simple_byom = byom_id.split("@")[0].strip()
    correo_byom_completo = f"{id_simple_byom}@byom.de"

    emitir_log("=== INICIANDO AUTOMATIZACIÓN EN EL SERVIDOR ===")

    driver = None
    try:
        driver = crear_driver()
        wait = WebDriverWait(driver, 20)

        # -------------------------------------------------------------
        # PASO 1: Login Microsoft / Outlook
        # -------------------------------------------------------------
        emitir_log("Paso 1: Abriendo Microsoft Login...")
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
        emitir_log("Paso 2: Abriendo Byom.de...")
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
        emitir_log("Paso 3: Enviando solicitud de código en Outlook...")
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
        emitir_log("Paso 4: Esperando correo en Byom.de...")
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
            emitir_log("ERROR: No se recibió el correo de verificación dentro del tiempo esperado.")
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
            emitir_log("ERROR: Se abrió el correo pero no se pudo extraer la secuencia numérica del código.")
            return

        codigo = match.group(1)
        emitir_log(f"¡Código capturado exitosamente!: {codigo}")

        # -------------------------------------------------------------
        # PASO 5: Pegar código en la pestaña de Outlook
        # -------------------------------------------------------------
        emitir_log("Paso 5: Ingresando código en la sesión de Outlook...")
        driver.switch_to.window(pestana_outlook)
        time.sleep(1)

        actions = ActionChains(driver)
        actions.send_keys(codigo).perform()
        time.sleep(0.5)
        actions.send_keys(Keys.ENTER).perform()

        # -------------------------------------------------------------
        # PASO 6: Pasar pantallas de confirmación (Passkey / Stay Signed In)
        # -------------------------------------------------------------
        emitir_log("Paso 6: Gestionando confirmaciones finales...")
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
                emitir_log("Respondido 'NO' en la confirmación de sesión activa.")
            except Exception:
                pass

        driver.get("https://outlook.live.com/mail/")
        emitir_log("=== ¡PROCESO COMPLETADO EXITOSAMENTE! ===")

    except Exception as e:
        emitir_log(f"Error inesperado durante la ejecución: {str(e)}")

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


@socketio.on('iniciar_proceso')
def handle_iniciar_proceso(json_data):
    correo = json_data.get('correo', '').strip()
    byom_id = json_data.get('byom_id', '').strip()

    if not correo or not byom_id:
        emitir_log("ERROR: Debes proporcionar tanto el correo como el ID de Byom.")
        return

    emitir_log(f"Recibida solicitud para el correo: {correo}")

    # Inicia la tarea en un hilo independiente para evitar bloqueos
    thread = threading.Thread(target=ejecutar_automatizacion, args=(correo, byom_id))
    thread.daemon = True
    thread.start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
