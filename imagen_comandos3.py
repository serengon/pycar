import pygame
import serial
import time
import cv2
from collections import deque

# ---------------- CONFIG ----------------
PUERTO = "COM4"
BAUDRATE = 115200
EJE_Q = 3
EJE_G = 2
BOTON_R = 9
BOTON_E = 5
INTERVALO = 0.1
DEADZONE = 0.05
ESCALA_VIDEO = 1.5
LINEAS_HISTORIAL = 4
# ----------------------------------------

# Serial
try:
    ser = serial.Serial(PUERTO, BAUDRATE, timeout=0.01)
    serial_ok = True
except:
    serial_ok = False

time.sleep(2)

# Cámara
cap = cv2.VideoCapture(0)

# Joystick
pygame.init()
pygame.joystick.init()
joy = None
joystick_ok = False

if pygame.joystick.get_count() > 0:
    joy = pygame.joystick.Joystick(0)
    joy.init()
    joystick_ok = True

ultimo_envio = 0
tx_hist = deque(maxlen=LINEAS_HISTORIAL)
rx_hist = deque(maxlen=LINEAS_HISTORIAL)

boton_r_activo = False
boton_e_activo = False

prev_time = time.time()

def aplicar_deadzone(valor, zona):
    if abs(valor) < zona:
        return 0
    return -valor

def dibujar_barra(frame, x, y, ancho, alto, valor, color):
    cv2.rectangle(frame, (x, y), (x+ancho, y+alto), (80,80,80), 1)
    centro = x + ancho // 2
    offset = int(valor * (ancho//2))
    cv2.rectangle(frame,
                  (centro, y),
                  (centro + offset, y+alto),
                  color, -1)

try:
    while True:
        ahora = time.time()
        dt = ahora - prev_time
        prev_time = ahora
        fps = 1.0 / dt if dt > 0 else 0

        ret, frame = cap.read()
        if not ret:
            break

        if ESCALA_VIDEO != 1.0:
            frame = cv2.resize(frame, None, fx=ESCALA_VIDEO, fy=ESCALA_VIDEO)

        valor_q = 0
        valor_g = 0

        # -------- EVENTOS --------
        for event in pygame.event.get():

            if event.type == pygame.JOYDEVICEADDED:
                joy = pygame.joystick.Joystick(0)
                joy.init()
                joystick_ok = True

            if event.type == pygame.JOYDEVICEREMOVED:
                joystick_ok = False
                joy = None

            if event.type == pygame.JOYBUTTONDOWN and joy:
                if event.button == BOTON_R:
                    boton_r_activo = True
                    if serial_ok:
                        ser.write(b"R\n")
                        tx_hist.appendleft("R")

                if event.button == BOTON_E:
                    boton_e_activo = True
                    if serial_ok:
                        ser.write(b"E\n")
                        tx_hist.appendleft("E")

            if event.type == pygame.JOYBUTTONUP:
                if event.button == BOTON_R:
                    boton_r_activo = False
                if event.button == BOTON_E:
                    boton_e_activo = False

        # -------- ENVÍO PERIÓDICO --------
        if joy and serial_ok and ahora - ultimo_envio >= INTERVALO:

            valor_q = aplicar_deadzone(joy.get_axis(EJE_Q), DEADZONE)
            valor_g = aplicar_deadzone(joy.get_axis(EJE_G), DEADZONE)

            mensaje = f"Q{valor_q:.2f} G{valor_g:.2f}"
            ser.write((mensaje + "\n").encode())
            tx_hist.append(mensaje)
            ultimo_envio = ahora

        # -------- RECEPCIÓN --------
        if serial_ok and ser.in_waiting > 0:
            linea = ser.readline().decode(errors="ignore").strip()
            if linea:
                rx_hist.append(linea)

        # -------- PANEL SUPERIOR --------
        overlay = frame.copy()
        cv2.rectangle(overlay, (10,10), (800,120), (0,0,0), -1)
        frame = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

        font_scale = 0.5
        thickness = 1

        # Historial TX
        cv2.putText(frame, "TX:", (20,35),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                    (0,255,0), thickness)

        for i, linea in enumerate(tx_hist):
            cv2.putText(frame, linea, (60,35+i*20),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                        (0,255,0), thickness)

        # Historial RX
        cv2.putText(frame, "RX:", (250,35),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                    (0,255,255), thickness)

        for i, linea in enumerate(rx_hist):
            cv2.putText(frame, linea, (290,35+i*20),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                        (0,255,255), thickness)

        # -------- LEDs ESTADO --------
        # Serial
        color_serial = (0,255,0) if serial_ok else (0,0,255)
        cv2.circle(frame, (700,30), 8, color_serial, -1)
        cv2.putText(frame, "SERIAL", (720,34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (255,255,255), 1)

        # Joystick
        color_joy = (0,255,0) if joystick_ok else (0,0,255)
        cv2.circle(frame, (700,50), 8, color_joy, -1)
        cv2.putText(frame, "JOYSTICK", (720,54),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (255,255,255), 1)

        # -------- BOTONES --------
        color_r = (0,255,0) if boton_r_activo else (100,100,100)
        cv2.circle(frame, (701,80), 10, color_r, -1)
        cv2.putText(frame, "R", (696,85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0,0,0), 1)

        color_e = (0,255,255) if boton_e_activo else (100,100,100)
        cv2.circle(frame, (730,80), 10, color_e, -1)
        cv2.putText(frame, "E", (725,85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0,0,0), 1)

        # -------- FPS --------
        cv2.putText(frame, f"FPS: {fps:.1f}",
                    (693,110),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255,255,255), 1)

        cv2.imshow("CONTROL STATION", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        time.sleep(0.005)

finally:
    cap.release()
    if serial_ok:
        ser.close()
    pygame.quit()
    cv2.destroyAllWindows()