def ejecutar_automatizacion(correo, byom_id):
    id_simple_byom = byom_id.split("@")[0]
    correo_byom_completo = f"{id_simple_byom}@byom.de"

    emitir_log("=== INICIANDO AUTOMATIZACIÓN EN EL SERVIDOR ===")

    chrome_options = webdriver.ChromeOptions()
    chrome_options.binary_location = "/usr/bin/google-chrome"
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 20)

        # Paso 1: Login Microsoft
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

        # Paso 2: Byom.de
        emitir_log("Paso 2: Consultando Byom.de...")
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

        # Paso 3: Enviar correo de recuperación
        emitir_log("Paso 3: Enviando solicitud de código...")
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

        # Paso 4: Extraer código
        emitir_log("Paso 4: Esperando código en Byom.de...")
        driver.switch_to.window(pestana_byom)
        correo_encontrado = False

        for _ in range(30):
            try:
                correo_ms = driver.find_element(
                    By.XPATH,
                    "//td[contains(.,'Microsoft account team') or contains(.,'Your single-use code')]",
                )
                if correo_ms.is_displayed():
                    correo_encontrado = True
                    time.sleep(4)
                    correo_ms.click()
                    break
            except Exception:
                pass
            time.sleep(2)

        if not correo_encontrado:
            emitir_log("ERROR: No se recibió el correo de verificación.")
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
            emitir_log("ERROR: No se pudo extraer el código.")
            return

        codigo = match.group(1)
        emitir_log(f"¡Código capturado!: {codigo}")

        # Paso 5: Pegar código
        driver.switch_to.window(pestana_outlook)
        time.sleep(1)

        actions = ActionChains(driver)
        actions.send_keys(codigo).perform()
        time.sleep(0.5)
        actions.send_keys(Keys.ENTER).perform()

        # Paso 6: Passkey y Stay Signed In
        emitir_log("Paso 6: Respondiendo confirmaciones finales...")
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
                emitir_log("Respondido 'NO' en Stay Signed In.")
            except Exception:
                pass

        driver.get("https://outlook.live.com/mail/")
        emitir_log("=== ¡PROCESO COMPLETADO EXITOSAMENTE EN LA WEB! ===")

    except Exception as e:
        emitir_log(f"Error en el proceso: {e}")
    finally:
        if driver:
            driver.quit()
