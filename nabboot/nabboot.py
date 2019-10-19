# Script executed at boot and at shutdown.
# At boot, set leds to orange and configure GPIOs (to prevent any motor to run)
# At shutdown, turn leds off.

from rpi_ws281x import Adafruit_NeoPixel, Color
import RPi.GPIO as GPIO
import sys

def set_leds(shutdown):
    LED_COUNT            = 5
    LED_PIN              = 13            # GPIO pin connected to the pixels (18 uses PWM!).
    LED_FREQ_HZ      = 800000    # LED signal frequency in hertz (usually 800khz)
    LED_DMA              = 12            # DMA channel to use for generating signal (try 10)
    LED_BRIGHTNESS = 200         # Set to 0 for darkest and 255 for brightest
    LED_INVERT       = False     # True to invert the signal (when using NPN transistor level shift)
    LED_CHANNEL      = 1             # set to '1' for GPIOs 13, 19, 41, 45 or 53

    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    # Intialize the library (must be called once before other functions).
    strip.begin()

    if shutdown:
        color = Color(0, 0, 0)
    else:
        color = Color(255, 128, 0)

    for led in range(6):
        strip.setPixelColor(led, color)

    strip.show()

def set_motors():
    MOTOR_CHANNELS = [[12, 11], [10, 9]]

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.cleanup()
    for pairs in MOTOR_CHANNELS:
        for channel in pairs:
            GPIO.setup(channel, GPIO.OUT)
            GPIO.output(channel, GPIO.LOW)

if __name__ == '__main__':
    shutdown = len(sys.argv) > 1 and sys.argv[1] == 'shutdown'
    set_leds(shutdown)
    set_motors()

