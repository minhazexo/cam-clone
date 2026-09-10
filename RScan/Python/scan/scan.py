import cv2 as cv
import numpy as np

'''
 Function to map values in range [in_min, in_max] to the range [out_min, out_max]
'''
def map(x, in_min, in_max, out_min, out_max):
	return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


# global variables for image ,blackPoint, whitePoint
img = None; whitePoint = None; blackPoint = None;


'''
 * High Pass Filter
 * Output of HPF depends on the kernel size provided as input argument
 * Links to the docuementation:
 *  Introduction: https://github.com/sourabhkhemka/DocumentScanner/wiki/Scan:-Introduction
 *  HPF: https://github.com/sourabhkhemka/DocumentScanner/wiki/GCMODE
 *
'''
def highPassFilter(kSize):
	global img
	
	print("applying high pass filter")
	
	if not kSize%2:
		kSize +=1
		
	kernel = np.ones((kSize,kSize),np.float32)/(kSize*kSize)
	
	filtered = cv.filter2D(img,-1,kernel)
	
	filtered = img.astype('float32') - filtered.astype('float32')
	filtered = filtered + np.full(img.shape, 127.0, dtype=np.float32)

	filtered = np.clip(filtered, 0, 255).astype('uint8')
	
	img = filtered
	
	# "img" now contains high pass filtered image.

	
	
'''
 * Method to select black point in the image
 *
 * Links to documentation: 
 *  Introduction: https://github.com/sourabhkhemka/DocumentScanner/wiki/Scan:-Introduction
 *  Black Point Select: https://github.com/sourabhkhemka/DocumentScanner/wiki/Black-Point-Select
''' 
def blackPointSelect():
	global img
	
	print("adjusting black point for final output ...")
	
	# refer repository's wiki page for detailed explanation

	img = img.astype('int32')

	img = map(img, blackPoint, 255, 0, 255)

	#if cv.__version__ == '3.4.4':
		#img = img.astype('uint8')

	_, img = cv.threshold(img, 0, 255, cv.THRESH_TOZERO)

	img = img.astype('uint8')
	

'''
 * Method to select whitePoint in the image
 *
 * Links to documentation: 
 *  Introduction: https://github.com/sourabhkhemka/DocumentScanner/wiki/Scan:-Introduction
 *  White Point Select: https://github.com/sourabhkhemka/DocumentScanner/wiki/White-Point-Select
'''
def whitePointSelect():
	global img
	
	print("white point selection running ...")

	# refer repository's wiki page for detailed explanation

	_,img = cv.threshold(img, whitePoint, 255, cv.THRESH_TRUNC)

	img = img.astype('int32')
	img = map(img, 0, whitePoint, 0, 255)
	img = img.astype('uint8')
	
	
'''
 * Method to select black point in the image
 *
 * Links to documentation: 
 *  Introduction: https://github.com/sourabhkhemka/DocumentScanner/wiki/Scan:-Introduction
 *  Black Point Select: https://github.com/sourabhkhemka/DocumentScanner/wiki/Black-Point-Select
 *
''' 
def blackAndWhite():
	global img
	
	# refer repository's wiki page for detailed explanation

	lab = cv.cvtColor(img, cv.COLOR_BGR2LAB)

	(l,a,b) = cv.split(lab)

	img = cv.add( cv.subtract(l,b), cv.subtract(l,a) )


def _map_array(x, in_min, in_max, out_min, out_max):
	"""Stateless version of map() for the functional API below."""
	x = np.asarray(x, dtype=np.float32)
	scale = (out_max - out_min) / float(in_max - in_min)
	return (x - in_min) * scale + out_min


def scan_image(image, mode="GCMODE", kSize=51, blackPoint=66, whitePoint=160):
	"""Scan a BGR image without globals (functional equivalent of this module).

	Modes: GCMODE (flatten + white/black, color preserved),
	RMODE (contrast stretch only), SMODE (contrast stretch + B&W).
	Returns a new uint8 BGR/gray image. Raises ValueError on bad input.
	"""
	if image is None or getattr(image, "size", 0) == 0:
		raise ValueError("empty input image")
	out = image.copy()
	ks = int(kSize)
	if ks % 2 == 0:
		ks += 1
	mode = str(mode).upper()
	if mode == "GCMODE":
		kernel = np.ones((ks, ks), np.float32) / float(ks * ks)
		background = cv.filter2D(out, -1, kernel)
		flat = out.astype(np.float32) - background.astype(np.float32) + 127.0
		out = np.clip(flat, 0, 255).astype(np.uint8)
		wp = 127.0
		_, out = cv.threshold(out, wp, 255, cv.THRESH_TRUNC)
		out = np.clip(_map_array(out, 0, wp, 0, 255), 0, 255).astype(np.uint8)
		bp = float(blackPoint)
		out = np.clip(_map_array(out, bp, 255, 0, 255), 0, 255)
		_, out = cv.threshold(out, 0, 255, cv.THRESH_TOZERO)
		return out.astype(np.uint8)
	elif mode == "RMODE":
		bp = float(blackPoint)
		out = np.clip(_map_array(out.astype(np.int32), bp, 255, 0, 255), 0, 255)
		_, out = cv.threshold(out, 0, 255, cv.THRESH_TOZERO)
		out = out.astype(np.uint8)
		wp = float(whitePoint)
		_, out = cv.threshold(out, wp, 255, cv.THRESH_TRUNC)
		return np.clip(_map_array(out.astype(np.int32), 0, wp, 0, 255), 0, 255).astype(np.uint8)
	elif mode == "SMODE":
		scanned = scan_image(image, mode="RMODE", blackPoint=blackPoint,
				     whitePoint=whitePoint)
		lab = cv.cvtColor(scanned, cv.COLOR_BGR2LAB)
		(l, a, b) = cv.split(lab)
		return cv.add(cv.subtract(l, b), cv.subtract(l, a))
	else:
		raise ValueError(f"unknown mode {mode!r} (expected GCMODE/RMODE/SMODE)")


def scan_photo_auto(image, **kwargs):
	"""Reference-quality scan with geometry fix (see auto_scan.py).

	Falls back to scan_image(GCMODE) if auto_scan is unavailable.
	"""
	try:
		from auto_scan import scan_photo_to_reference
		return scan_photo_to_reference(image, **kwargs)
	except Exception:
		return scan_image(image, mode="GCMODE")


if __name__ == "__main__":
	import argparse
	import os

	parser = argparse.ArgumentParser(description="RScan single-image scanner")
	parser.add_argument("--input", default=None, help="input image path")
	parser.add_argument("--output", default=None, help="output image path")
	parser.add_argument("--mode", default="GCMODE",
			    help="GCMODE/RMODE/SMODE/AUTO (AUTO=reference-quality, recommended)")
	parser.add_argument("--ksize", type=int, default=51)
	parser.add_argument("--black-point", type=float, default=66)
	parser.add_argument("--white-point", type=float, default=160)
	args = parser.parse_args()

	if args.input is None:
		# Legacy behavior (original hardcoded demo). Kept so old scripts
		# that relied on module globals keep working; prefer --input.
		img = cv.imread("C:/Users/Sourabh Khemka/Desktop/RScan/ML/dataset/data_img_008.jpg")
		blackPoint = 66
		whitePoint = 160
		mode = "GCMODE"
		if img is None:
			raise SystemExit("legacy demo image not found; re-run with --input <image>")
		if mode == "GCMODE":
			highPassFilter(kSize=51)
			whitePoint = 127
			whitePointSelect()
			blackPointSelect()
		elif mode == "RMODE":
			blackPointSelect()
			whitePointSelect()
		elif mode == "SMODE":
			blackPointSelect()
			whitePointSelect()
			blackAndWhite()
		print("\ndone.")
		cv.imwrite('C:/Users/Sourabh Khemka/Desktop/RScan/ML/op.jpg', img)
	else:
		src = cv.imread(args.input, cv.IMREAD_COLOR)
		if src is None:
			raise SystemExit(f"could not read input image: {args.input}")
		if args.mode.upper() == "AUTO":
			result = scan_photo_auto(src)
		else:
			result = scan_image(src, mode=args.mode, kSize=args.ksize,
					    blackPoint=args.black_point,
					    whitePoint=args.white_point)
		out_path = args.output or (os.path.splitext(args.input)[0] + "_scanned.jpg")
		cv.imwrite(out_path, result)
		print(f"\ndone. wrote {out_path}")
