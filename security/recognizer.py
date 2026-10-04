"""Face detection (Haar cascade) + recognition (LBPH) - deliberately
lightweight for the Pi 4B's 1.8GB RAM (see docs/HOME-SECURITY.md's future
work for the DNN-detector / dlib-embedding upgrade path).

The cascade XML is bundled in this directory rather than loaded from
cv2.data.haarcascades - the opencv-contrib-python-headless wheel piwheels
serves for this platform ships an empty cv2/data/ (no XML files at all),
so that path doesn't exist here even though it does on most other
platforms.
"""
import os

import cv2
import numpy as np

import config

FACE_SIZE = (200, 200)
_CASCADE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "haarcascade_frontalface_default.xml")

_cascade = cv2.CascadeClassifier(_CASCADE_PATH)
if _cascade.empty():
    raise RuntimeError(f"failed to load Haar cascade from {_CASCADE_PATH}")


def detect_faces(gray_frame):
    """Returns a list of (x, y, w, h) boxes for every face found."""
    return _cascade.detectMultiScale(
        gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
    )


def crop_face(gray_frame, box):
    x, y, w, h = box
    face = gray_frame[y : y + h, x : x + w]
    return cv2.resize(face, FACE_SIZE)


class Recognizer:
    """Trains once from the current known_people table (call reload() to
    pick up people added/removed since). Untrained (no one enrolled yet)
    means every detected face is reported unknown, by design."""

    def __init__(self):
        self._model = cv2.face.LBPHFaceRecognizer_create()
        self._label_to_name = {}
        self._trained = False

    def reload(self, known_people):
        """known_people: rows with .id, .name, .photo_path (id doubles as
        the LBPH numeric label - stable across reloads)."""
        faces = []
        labels = []
        self._label_to_name = {}
        for person in known_people:
            img = cv2.imread(person["photo_path"], cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            boxes = detect_faces(img)
            if len(boxes) == 0:
                continue
            face = crop_face(img, boxes[0])
            faces.append(face)
            labels.append(person["id"])
            self._label_to_name[person["id"]] = person["name"]

        if faces:
            self._model.train(faces, np.array(labels))
            self._trained = True
        else:
            self._trained = False

    def identify(self, gray_frame, box, threshold=None):
        """Returns (status, name, confidence) - status is "known" or
        "unknown", confidence is LBPH's raw distance (lower = closer
        match) or None if untrained (nothing to compare against).
        threshold overrides config.LBPH_CONFIDENCE_THRESHOLD - monitor.py
        passes the live, settings-page-editable value each cycle."""
        if not self._trained:
            return "unknown", None, None
        face = crop_face(gray_frame, box)
        label, confidence = self._model.predict(face)
        limit = config.LBPH_CONFIDENCE_THRESHOLD if threshold is None else threshold
        if confidence <= limit:
            return "known", self._label_to_name.get(label), confidence
        return "unknown", None, confidence
