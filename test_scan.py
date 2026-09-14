#!/usr/bin/env python3
"""Test script for RScan APIs."""
import urllib.request
import urllib.error
import json
import os
import sys
import time

BASE = "http://localhost:5000"

def test_image_scan(image_path):
    """Test the /api/scan endpoint with a single image."""
    print(f"\n=== Testing Image Scan: {os.path.basename(image_path)} ===")
    if not os.path.exists(image_path):
        print(f"ERROR: File not found: {image_path}")
        return False
    
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = b''
    body += f'--{boundary}\r\n'.encode()
    body += f'Content-Disposition: form-data; name="files"; filename="{os.path.basename(image_path)}"\r\n'.encode()
    body += b'Content-Type: image/jpeg\r\n'
    body += b'\r\n'
    with open(image_path, 'rb') as f:
        body += f.read()
    body += b'\r\n'
    body += f'--{boundary}--\r\n'.encode()
    
    req = urllib.request.Request(
        f"{BASE}/api/scan",
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        method='POST'
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        pages = data.get('pages', [])
        print(f"SUCCESS: Got {len(pages)} result(s)")
        for p in pages:
            print(f"  - {p.get('name')}: id={p.get('id')}, {p.get('width')}x{p.get('height')}px")
        return len(pages) == 1
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_pdf_scan(pdf_path):
    """Test the /api/scan-pdf endpoint."""
    print(f"\n=== Testing PDF Scan: {os.path.basename(pdf_path)} ===")
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        return False
    
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = b''
    body += f'--{boundary}\r\n'.encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(pdf_path)}"\r\n'.encode()
    body += b'Content-Type: application/pdf\r\n'
    body += b'\r\n'
    with open(pdf_path, 'rb') as f:
        body += f.read()
    body += b'\r\n'
    body += f'--{boundary}--\r\n'.encode()
    
    req = urllib.request.Request(
        f"{BASE}/api/scan-pdf",
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        method='POST'
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=300)
        data = json.loads(resp.read())
        pdf_name = data.get('pdf', '')
        print(f"SUCCESS: PDF scan complete, output={pdf_name}")
        return True
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Test 1: Single image scan
    img_path = os.path.join(base_dir, 'IMG-20260905-WA0005.jpg')
    img_ok = test_image_scan(img_path)
    
    # Test 2: PDF scan
    pdf_path = os.path.join(base_dir, 'EMON {PHA 205 (WOAM) }.pdf')
    pdf_ok = test_pdf_scan(pdf_path)
    
    print(f"\n=== Results ===")
    print(f"Image Scan: {'PASS' if img_ok else 'FAIL'}")
    print(f"PDF Scan: {'PASS' if pdf_ok else 'FAIL'}")
    sys.exit(0 if (img_ok and pdf_ok) else 1)