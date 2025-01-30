import sys
import cv2
import numpy as np
import threading
import queue
from tkinter import Tk, Button, Label, Frame, Scale, HORIZONTAL, messagebox, filedialog
from PIL import Image, ImageTk, ImageDraw
import gxipy as gx


class DahengCameraGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Daheng Camera Control")
        self.root.geometry("1280x720")  # Set window size to 1280x720

        # Initialize camera variables
        self.device_manager = None
        self.cam = None
        self.is_streaming = False
        self.current_exposure = 10000.0  # Default exposure time in microseconds

        # Create a queue for frame communication between threads
        self.frame_queue = queue.Queue(maxsize=2)

        # Main container frame
        main_frame = Frame(self.root)
        main_frame.pack(fill="both", expand=True)

        # Left panel for buttons and slider
        left_panel = Frame(main_frame, width=200)
        left_panel.pack(side="left", fill="y", padx=5, pady=5)

        # Create buttons
        self.btn_connect = Button(left_panel, text="Connect Camera", command=self.connect_camera)
        self.btn_start = Button(left_panel, text="Start Acquisition", command=self.start_acquisition)
        self.btn_stop = Button(left_panel, text="Stop Acquisition", command=self.stop_acquisition)
        self.btn_save = Button(left_panel, text="Save Image", command=self.save_image)
        self.btn_close = Button(left_panel, text="Close Camera", command=self.close_camera)

        # Disable buttons initially
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.btn_save.config(state="disabled")
        self.btn_close.config(state="disabled")

        # Pack buttons vertically
        self.btn_connect.pack(fill="x", pady=5)
        self.btn_start.pack(fill="x", pady=5)
        self.btn_stop.pack(fill="x", pady=5)
        self.btn_save.pack(fill="x", pady=5)
        self.btn_close.pack(fill="x", pady=5)

        # Create a slider for exposure adjustment
        self.exposure_slider = Scale(left_panel, from_=1000, to=100000, orient=HORIZONTAL, label="Exposure Time (μs):")
        self.exposure_slider.set(int(self.current_exposure))  # Set initial value
        self.exposure_slider.config(command=self.update_exposure)
        self.exposure_slider.pack(fill="x", pady=5)

        # Right panel for camera feed
        right_panel = Frame(main_frame)
        right_panel.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        # Create a Label to display the camera feed
        self.image_label = Label(right_panel, text="Camera feed will appear here", bg="black", fg="white")
        self.image_label.pack(fill="both", expand=True)

        # Initialize threads
        self.acquisition_thread = None
        self.processing_thread = None

    def connect_camera(self):
        """Connect to the Daheng camera and configure settings."""
        try:
            self.device_manager = gx.DeviceManager()
            dev_num, dev_info_list = self.device_manager.update_device_list()
            if dev_num == 0:
                messagebox.showwarning("Error", "No cameras found.")
                return

            self.cam = self.device_manager.open_device_by_sn(dev_info_list[0].get("sn"))

            if self.cam.Width.is_implemented() and self.cam.Width.is_writable() and \
               self.cam.Height.is_implemented() and self.cam.Height.is_writable():
                self.cam.Width.set(4096)  # Set width to 4096
                self.cam.Height.set(3000)  # Set height to 3000
                messagebox.showinfo("Success", "Resolution set to 4096x3000")
            else:
                messagebox.showwarning("Warning", "Resolution control is not supported by this camera.")

            if self.cam.AcquisitionFrameRate.is_implemented() and self.cam.AcquisitionFrameRate.is_writable():
                self.cam.AcquisitionFrameRate.set(1.0)  # Set frame rate to 1 FPS
                messagebox.showinfo("Success", "Frame Rate Set to 1 FPS")
            else:
                messagebox.showwarning("Warning", "Frame rate control is not supported by this camera.")

            if self.cam.ExposureTime.is_implemented() and self.cam.ExposureTime.is_writable():
                self.cam.ExposureTime.set(self.current_exposure)  # Set initial exposure time
                messagebox.showinfo("Success", f"Exposure Time Set to {self.current_exposure} μs")
            else:
                messagebox.showwarning("Warning", "Exposure time control is not supported by this camera.")

            self.btn_start.config(state="normal")
            self.btn_connect.config(state="disabled")
            self.btn_close.config(state="normal")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect: {str(e)}")

    def start_acquisition(self):
        """Start camera acquisition and processing threads."""
        if self.cam is None:
            messagebox.showwarning("Error", "Camera not connected.")
            return

        try:
            self.cam.stream_on()
            self.is_streaming = True
            self.btn_stop.config(state="normal")
            self.btn_save.config(state="normal")
            self.btn_start.config(state="disabled")
            messagebox.showinfo("Success", "Acquisition Started at 1 FPS (4096x3000)")

            self.acquisition_thread = threading.Thread(target=self.acquire_frames)
            self.acquisition_thread.start()

            self.processing_thread = threading.Thread(target=self.process_frames)
            self.processing_thread.start()

            self.update_frame()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start acquisition: {str(e)}")

    def stop_acquisition(self):
        """Stop camera acquisition and clear buffers."""
        if self.cam is None or not self.is_streaming:
            return

        try:
            self.cam.stream_off()
            self.is_streaming = False
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            messagebox.showinfo("Success", "Acquisition Stopped")

            self.frame_queue.queue.clear()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to stop acquisition: {str(e)}")

    def acquire_frames(self):
        """Acquire frames from the camera and put them in the queue."""
        while self.is_streaming:
            try:
                raw_image = self.cam.data_stream[0].get_image()
                if raw_image.get_status() == gx.GxFrameStatusList.INCOMPLETE:
                    continue
                self.frame_queue.put(raw_image)
            except Exception as e:
                print(f"Error acquiring frame: {str(e)}")

    def process_frames(self):
        """Process frames from the queue and update the GUI."""
        while self.is_streaming:
            try:
                raw_image = self.frame_queue.get()
                rgb_image = raw_image.convert("RGB")
                if rgb_image is None:
                    continue

                numpy_image = rgb_image.get_numpy_array()
                if numpy_image is None:
                    continue

                resized_image = cv2.resize(numpy_image, (1280, 720))
                centroid, diameter, circularity = self.calculate_centroid(resized_image)

                if centroid:
                    cx_resized, cy_resized = centroid
                    scale_x = 4096 / 1280
                    scale_y = 3000 / 720
                    cx_original = int(cx_resized * scale_x)
                    cy_original = int(cy_resized * scale_y)
                else:
                    cx_original, cy_original = None, None

                pil_image = Image.fromarray(resized_image)
                draw = ImageDraw.Draw(pil_image)
                draw.line((0, 360, 1280, 360), fill=(255, 0, 0), width=2)  # X-axis
                draw.line((640, 0, 640, 720), fill=(255, 0, 0), width=2)  # Y-axis

                if centroid:
                    cx, cy = centroid
                    draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), outline=(255, 0, 0), width=2)
                    draw.text((cx + 10, cy + 10), f"({cx_original}, {cy_original})", fill=(255, 0, 0))
                    draw.text((10, 20), f"Diameter: {diameter:.2f} px", fill=(255, 0, 0))
                    draw.text((10, 40), f"Circularity: {circularity:.2f}", fill=(255, 0, 0))

                tk_image = ImageTk.PhotoImage(pil_image)
                self.image_label.config(image=tk_image)
                self.image_label.image = tk_image
            except Exception as e:
                print(f"Error processing frame: {str(e)}")

    def update_exposure(self, value):
        """Update the exposure time dynamically."""
        if self.cam is not None and self.is_streaming:
            try:
                self.current_exposure = float(value)
                self.cam.ExposureTime.set(self.current_exposure)
                print(f"Exposure Time Updated to {self.current_exposure} μs")
            except Exception as e:
                print(f"Failed to update exposure time: {str(e)}")

    def update_frame(self):
        """Periodically update the GUI with the latest frame."""
        if self.is_streaming:
            self.root.after(200, self.update_frame)

    def calculate_centroid(self, image):
        """Calculate the centroid, diameter, and circularity of the largest object in the image."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresholded_image = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(thresholded_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest_contour = max(contours, key=cv2.contourArea)
            moments = cv2.moments(largest_contour)
            if moments["m00"] != 0:
                cx = int(moments["m10"] / moments["m00"])
                cy = int(moments["m01"] / moments["m00"])
                area = cv2.contourArea(largest_contour)
                diameter = np.sqrt(4 * area / np.pi)
                perimeter = cv2.arcLength(largest_contour, True)
                circularity = float(4 * np.pi * (area / (perimeter * perimeter)))
                return (cx, cy), diameter, circularity
        return None, 0, 0

    def save_image(self):
        """Save the current frame as an image file."""
        if not self.is_streaming:
            messagebox.showwarning("Error", "Acquisition is not running.")
            return

        try:
            raw_image = self.cam.data_stream[0].get_image()
            if raw_image.get_status() == gx.GxFrameStatusList.INCOMPLETE:
                messagebox.showwarning("Error", "Incomplete frame.")
                return

            rgb_image = raw_image.convert("RGB")
            if rgb_image is None:
                messagebox.showwarning("Error", "Failed to convert image to RGB.")
                return

            numpy_image = rgb_image.get_numpy_array()
            if numpy_image is None:
                messagebox.showwarning("Error", "Failed to get numpy array.")
                return

            pil_image = Image.fromarray(numpy_image, 'RGB')
            file_path = filedialog.asksaveasfilename(defaultextension=".jpg", filetypes=[("JPEG Files", "*.jpg"), ("All Files", "*.*")])
            if file_path:
                pil_image.save(file_path)
                messagebox.showinfo("Success", f"Image saved to {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save image: {str(e)}")

    def close_camera(self):
        """Close the camera and release resources."""
        if self.cam is not None:
            try:
                if self.is_streaming:
                    self.cam.stream_off()
                self.cam.close_device()
                self.device_manager = None
                self.cam = None
                self.is_streaming = False
                self.btn_start.config(state="disabled")
                self.btn_stop.config(state="disabled")
                self.btn_save.config(state="disabled")
                self.btn_close.config(state="disabled")
                self.btn_connect.config(state="normal")
                messagebox.showinfo("Info", "Camera closed.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to close camera: {str(e)}")

    def closeEvent(self):
        """Handle application close event."""
        self.close_camera()
        self.root.destroy()


if __name__ == "__main__":
    root = Tk()
    app = DahengCameraGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.closeEvent)
    root.mainloop()