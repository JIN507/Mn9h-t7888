import asyncio
import urllib.request
from pydub import AudioSegment
import speech_recognition as sr
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def handle_recaptcha(page):
    """
    Handles reCAPTCHA by solving the audio challenge automatically.
    This function can be called whenever a captcha appears during TheHive.ai scraping.
    
    Args:
        page: The Playwright page object where the captcha appears
        
    Returns:
        bool: True if captcha was successfully solved, False otherwise
    """
    try:
        logger.info("[*] Handling reCAPTCHA...")

        # Create temp directory for audio files if it doesn't exist
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # File paths
        mp3_path = os.path.join(temp_dir, "captcha.mp3")
        wav_path = os.path.join(temp_dir, "captcha.wav")

        # Switch to the first iframe that contains the checkbox
        frame = page.frame_locator('iframe[src*="recaptcha"]').first

        # Wait and click the checkbox
        recaptcha_checkbox = frame.locator('.recaptcha-checkbox-border')
        await recaptcha_checkbox.wait_for(state='visible', timeout=30000)
        await recaptcha_checkbox.click()
        await asyncio.sleep(5)

        # Switch to audio challenge iframe
        audio_frame = page.frame_locator('iframe').nth(2)
        audio_button = audio_frame.locator('#recaptcha-audio-button')
        await audio_button.wait_for(state='visible', timeout=30000)
        await audio_button.click()
        await asyncio.sleep(2)

        # Get audio source URL
        src = await audio_frame.locator('#audio-source').get_attribute('src')
        urllib.request.urlretrieve(src, mp3_path)
        logger.info(f"[*] Downloaded audio to {mp3_path}")

        # Convert MP3 to WAV
        AudioSegment.from_mp3(mp3_path).export(wav_path, format='wav')
        logger.info(f"[*] Converted to WAV: {wav_path}")

        # Transcribe audio using Google Speech Recognition
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        transcription = recognizer.recognize_google(audio_data)
        logger.info(f"[*] Transcription: {transcription}")

        # Enter response
        response_input = audio_frame.locator('#audio-response')
        await response_input.fill(transcription)
        await asyncio.sleep(2)

        # Submit verification
        verify_button = audio_frame.locator('#recaptcha-verify-button')
        await verify_button.click()
        await asyncio.sleep(2)

        logger.info("[+] reCAPTCHA passed!")
        return True

    except Exception as e:
        logger.error(f"[!] Error handling reCAPTCHA: {e}")
        return False
    finally:
        # Clean up temporary files
        try:
            if os.path.exists(mp3_path):
                os.remove(mp3_path)
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except Exception as e:
            logger.warning(f"[!] Error cleaning up temporary files: {e}")

# Synchronous wrapper for handling recaptcha in non-async code
def solve_captcha(page):
    """
    Synchronous wrapper for handle_recaptcha to use in non-async code.
    
    Args:
        page: The Playwright page object where the captcha appears
        
    Returns:
        bool: True if captcha was successfully solved, False otherwise
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If no event loop is available, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(handle_recaptcha(page))
