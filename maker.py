#!/bin/python3
import io, sys, os
from collections import defaultdict

defaultPath = "default.jpg"

print("NRO Asset Editor v1.2")
config = defaultdict(None)
sys.argv += [ None ] * 2

try:
	from PIL import Image
	hasPIL = True
except:
	hasPIL = False
	print("[WARNING] No Python Image Library installed, cannot use --icon! To resolve, try: pip3 install Pillow")

hasGUI = False
for x in range(1, len(sys.argv), 2):
	arg = sys.argv[x]
	if arg and arg[2:] in [ "title", "author", "version", "icon", "nro" ]:
		config[arg[2:]] = sys.argv[x + 1]

if len(config) == 0:
	print("usage:\n\tpython3 maker.py [--nro /path/to/file.nro] [--title \"Your App Title\"] [--icon /path/to/icon.(png|jpg)] [--author \"Your Author\"] [--version x.x.x]")
	print("\tNo valid arguments specified, going to run GUI!")
	hasGUI = True
else:
	print("Entering command line mode! To start the GUI don't provide any args.")

if hasGUI:
	try:
		import tkinter as tk
		from tkinter import filedialog
		from PIL import ImageTk
	except:
		print("[ERROR] TKinter not installed! Cannot display GUI. You can still use the command-line mode by specifying arguments.")
		exit(1)

try:
	defaultPath = sys._MEIPASS + os.path.sep + defaultPath + os.path.sep + defaultPath
except:
	pass

class Asset:
	def __init__(self, offset):
		# initialize icon, nacp, and romfs
		self.nacp = bytearray([])
		self.icon = bytearray([])
		self.romfs = bytearray([])

		# offset is the total size of the .nro excluding these asset section
		self.offset = offset

	# load this asset object with data from a bunch of bytes
	# at the end of a .nro file (after the nro.size)
	def load(self, data):
		# get icon data
		offset = 0x4 + 0x4

		icon_pos = int.from_bytes(data[offset:offset+0x8], "little")
		icon_size = int.from_bytes(data[offset+0x8:offset+0x10], "little")
		self.icon += data[icon_pos:icon_pos+icon_size]
		offset += 0x10

		nacp_pos = int.from_bytes(data[offset:offset+0x8], "little")
		nacp_size = int.from_bytes(data[offset+0x8:offset+0x10], "little")
		self.nacp += data[nacp_pos:nacp_pos+nacp_size]
		offset += 0x10

		romfs_pos = int.from_bytes(data[offset:offset+0x8], "little")
		romfs_size = int.from_bytes(data[offset+0x8:offset+0x10], "little")
		self.romfs += data[romfs_pos:romfs_pos+romfs_size]
		offset += 0x10

		# we need to load human readable strings out of the nacp
		self.name    = self.nacp[0:0x200].decode("utf-8").strip("\x00")
		self.author =  self.nacp[0x200:0x300].decode("utf-8").strip("\x00")
		self.version = self.nacp[0x3060:0x3070].decode("utf-8").strip("\x00")

	def updateNACP(self, editor, config):

		if hasGUI:
			my_name = editor.name.get()
			my_author = editor.author.get()
			my_version = editor.version.get()
		else:
			my_name = config["title"]
			my_author = config["author"]
			my_version = config["version"]

		# NACP should have size 0x4000, extend the byte array if this is not already true
		if len(self.nacp) < 0x4000:
			self.nacp += bytearray([0]*(0x4000 - len(self.nacp)))

		# TODO: fill out some more fields? http://switchbrew.org/index.php?title=Control.
		# we're only going to fill out name, author, and version using as much
		# existing information as possible

		# 15 languages (app name + author)
		for x in range(15):
			app_name = bytearray(my_name, encoding="utf-8")			# get user-input string
			app_name += bytearray([0]*(0x200 - len(app_name)))		# pad 0s until 0x200
			self.nacp[x*0x300:(x*0x300+0x200)] = app_name			# insert into nacp

			author = bytearray(my_author, encoding="utf-8")			# get user-input string
			author += bytearray([0]*(0x100 - len(author)))			# pad 0s until 0x100
			self.nacp[x*0x300+0x200:(x*0x300+0x300)] = author		# insert into nacp

		# version
		version = bytearray(my_version, encoding="utf-8")
		version += bytearray([0]*(0x10 - len(version)))
		self.nacp[0x3060:0x3060+0x10] = version

	# return the bytes that makeup this object, based on the fields
	def getBytes(self):
		# asset header magic
		ret = b"ASET"
		ret += bytearray([0, 0, 0, 0])

		# total size of asset header
		offset = 0x38

		# first asset section, icon
		icon_size = len(self.icon)

		if icon_size > 0:
			ret += (offset).to_bytes(8, "little")
			ret += (icon_size).to_bytes(8, "little")
		else:
			ret += bytearray([0]*0x10)
		offset += icon_size

		# 2nd asset section, nacp metadata
		nacp_size = len(self.nacp)

		if nacp_size > 0:
			ret += (offset).to_bytes(8, "little")
			ret += (nacp_size).to_bytes(8, "little")
		else:
			ret += bytearray([0]*0x10)
		offset += nacp_size

		# 3rd asset section, romfs
		romfs_size = len(self.romfs)

		if romfs_size > 0:
			ret += (offset).to_bytes(8, "little")
			ret += (romfs_size).to_bytes(8, "little")
		else:
			ret += bytearray([0]*0x10)
		offset += romfs_size

		# write data bytes
		ret += self.icon
		ret += self.nacp
		ret += self.romfs

		# all done
		return ret

class Editor:
	def __init__(self, elems=[]):
		self.filename = None
		self.elements = elems

		if hasGUI:
			self.name = tk.StringVar()
			self.name.set("Untitled Homebrew")
			self.author = tk.StringVar()
			self.author.set("Unknown Author")
			self.version = tk.StringVar()
			self.version.set("0.0.0")

		self.image = None
		self.data = None
		self.nrosize = 0
	
	def loadImageData(self, img_url):
		self.image = Image.open(img_url).convert("RGB")
		self.image = self.image.resize((256, 256), Image.ANTIALIAS)

		buffer = io.BytesIO()
		# if it's not already a jpeg, convert it into one
		if self.image.format != "JPEG":
			self.image.save(buffer, format="JPEG")
			self.image = Image.open(buffer)

	# prompt for an image file
	def browse_image(self):
		# load either the new image or the default one
		img_url = filedialog.askopenfilename(title = "Select image file",filetypes = (("PNG Files","*.png"),("JPG Files","*.jpg"),("JPEG Files","*.jpeg"), ("GIF Files","*.gif"), ("BMP Files","*.bmp"), ("TGA Files","*.tga"), ("All Files","*.*"))) or defaultPath

		loadImageData(img_url)

		image2 = ImageTk.PhotoImage(self.image)
		self.imagebox.configure(image=image2)
		self.imagebox.image = image2

	# update the current NRO with the new asset data
	def saveNRO(self, config={}):

		# update any of our asset header values based on what's
		# been typed in the entry boxes, or the new icon

		# icon, read out currently displayed jpeg to bytes
		# quality=keep is needed so it doesn't re-jpeg-ify
		if hasPIL:
			buffer = io.BytesIO()
			self.image.save(buffer, format="JPEG", quality="keep")
			self.asset.icon = bytearray(buffer.getvalue())

		# metadata, get currently displayed values and isnert
		# them into every language
		self.asset.updateNACP(self, config)

		# get the asset bytes so we can verify they're there first
		assetbytes = self.asset.getBytes()

		if assetbytes:
			with open(self.filename, "wb") as nro:
				nro.write(self.data)
				nro.write(assetbytes)
				nro.flush()
		else:
			# failed
			return False

		return True

	def loadBinaryData(self):
		# load out some info
		with open(self.filename, "rb") as binary:
			self.data = binary.read()
			data = self.data

			# verify NRO0 format
			if data[0x10:0x14] != b"NRO0":
				return False

			# get the filesize, so we can go to the assets section
			self.nrosize = int.from_bytes(data[0x18:0x1C], byteorder="little")
			size = self.nrosize

			# check for ASET data
			self.asset = Asset(size)
			asset = self.asset

			if len(data) > size+4 and data[size:size+0x4] == B"ASET":
				# load the asset data
				self.asset.load(bytearray(data[size:]))

				if hasPIL:
					self.image = Image.open(io.BytesIO(asset.icon))

				# truncate the old assset data from memory
				self.data = data[:size]

	# prompt for a file browser to select a .NRO file to extract data from
	def browse(self):
		self.filename = filedialog.askopenfilename(title = "Select NRO",filetypes = (("NRO Files","*.nro"),("All Files","*.*"))) or self.filename

		self.loadBinaryData()

		self.name.set(asset.name)
		self.author.set(asset.author)
		self.version.set(asset.version)
		
		image2 = ImageTk.PhotoImage(self.image)
		self.imagebox.configure(image=image2)
		self.imagebox.image = image2


		if self.filename:
			# enable all buttons and fields
			self.elements[0].configure(state = "active")
			for elem in self.elements[1:]:
				elem.configure(state = "normal")


if hasGUI:
	root = tk.Tk()
	root.title("NRO Asset Editor")

	# batch of UI input elements
	elems = []
	editor = Editor(elems)

	# frame containing load and save buttons
	fileframe = tk.Frame(root)
	fileframe.grid(row=0, column=2, columnspan=1)

	tk.Button(fileframe, text="Load NRO...", command=editor.browse).grid(row=0, column=0)
	saveb = tk.Button(fileframe, text="Save", state="disabled", command=editor.saveNRO)
	saveb.grid(row=0, column=1)
	elems.append(saveb)

	frame = tk.Frame(root)
	frame.grid(row=3, column=2, columnspan=2)

	# main text entry boxes (disabled by default)
	tk.Label(frame, text="App Name").grid(row=0, column=0, padx=5)
	t1 = tk.Entry(frame, state="disabled", textvariable=editor.name)
	t1.grid(row=0, column=1, padx=5)
	elems.append(t1)

	tk.Label(frame, text="Author").grid(row=1, column=0, padx=5)
	t2 = tk.Entry(frame, state="disabled", textvariable=editor.author)
	t2.grid(row=1, column=1, padx=5)
	elems.append(t2)

	tk.Label(frame, text="Version").grid(row=2, column=0, padx=5)
	t3 = tk.Entry(frame, state="disabled", textvariable=editor.version)
	t3.grid(row=2, column=1, padx=5)
	elems.append(t3)

	b1 = tk.Button(frame, text="Open Image...", state="disabled", command=editor.browse_image)
	b1.grid(row=3, column=1, padx=(50, 5))
	elems.append(b1)

	# icon preview
	im = Image.open(defaultPath)
	tkimage = ImageTk.PhotoImage(im)

	canvas = tk.Label(frame, image=tkimage, width=256, height=256)
	canvas.grid(row=0, rowspan=8, column=2)
	editor.imagebox = canvas

	root.geometry("550x300")
	root.resizable(0, 0)

	root.mainloop()

else:
	nro = config["nro"]
	del config["nro"]
	if not nro:
		print("[ERROR] No nro file specified, please provide one with --nro /path/file.nro")
		exit(1)
	print(f"-> Opening '{nro}'...")

	opDone = False
	editor = Editor()
	editor.filename = nro
	editor.loadBinaryData()

	asset = editor.asset

	print(f"-> Original Metadata:")
	print(f"--> Title: {asset.name}")
	print(f"--> Author: {asset.author}")
	print(f"--> Version: {asset.version}")

	if "icon" in config.keys():
		if hasPIL:
			editor.loadImageData(config[icon])
			printf(f"-> Going to update the icon to {config[icon]}!")
		else:
			print("[ERROR] No PIL installed, cannot accept '--icon' argument")
			exit(2)

	# fill out missing keys based on existing data
	for key in ["title", "author", "version"]:
		if key in config:
			# at least one of these three was given
			opDone = True
		else:
			if key == "title":
				config["title"] = asset.name
			if key == "author":
				config["author"] = asset.author
			if key == "version":
				config["version"] = asset.version
	
	if opDone:
		print(f"-> Saving '{nro}'...")
		editor.saveNRO(config)

		# load it again so we can show the new values
		e2 = Editor()
		e2.filename = editor.filename
		e2.loadBinaryData()
		asset = e2.asset
		print(f"-> NRO was updated!")
		print(f"-> New Metadata:")
		print(f"--> Title: {asset.name}")
		print(f"--> Author: {asset.author}")
		print(f"--> Version: {asset.version}")
	else:
		print("[WARNING] No changes were made")
