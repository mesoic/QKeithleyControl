# ---------------------------------------------------------------------------------
# 	QKeithleyControl
# 	Copyright (C) 2019 Michael Winters
#	mwchalmers@protonmail.com
# ---------------------------------------------------------------------------------
# 
# 	Permission is hereby granted, free of charge, to any person obtaining a copy
# 	of this software and associated documentation files (the "Software"), to deal
# 	in the Software without restriction, including without limitation the rights
# 	to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# 	copies of the Software, and to permit persons to whom the Software is
# 	furnished to do so, subject to the following conditions:
# 	
# 	The above copyright notice and this permission notice shall be included in all
# 	copies or substantial portions of the Software.
# 	
# 	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# 	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# 	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# 	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# 	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# 	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# 	SOFTWARE.
#

#!/usr/bin/env python 
import visa
import time
import numpy as np
import threading

# Import d_plot and keithley driver
import drivers.keithley_2400
import widgets.QDynamicPlot 

# Import QT backends
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox, QLabel, QFileDialog
from PyQt5.QtCore import Qt, QStateMachine, QState, QObject

# Import matplotlibQT backends
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt

# Container class to construct sweep measurement widget
class QKeithleySweep(QWidget):

	def __init__(self):

		# Inherits QWidget
		QWidget.__init__(self)	

		# Initialize Keithley Object
		self.keithley = None

		# Create objects to hold data
		self._data = []
		self.sweep = []

		# Create layout objects and set layout
		self.layout = QHBoxLayout()
		self.layout.addLayout(self._gen_sweep_layout())
		self.layout.addLayout(self._gen_sweep_plot())
		self.setLayout(self.layout)

	# Set visa insturment handle for keithley
	def _set_keithley_handle(self, keithley):
		self.keithley=keithley

	# Method to set sweep parameters
	def _set_sweep_params(self, _start, _stop, _points, _hist=False):
		_ = np.linspace(float(_start), float(_stop), int(_points))
		self.sweep = np.concatenate((_,_[-2::-1])) if _hist else _

	# Method to get sweep parameters
	def _get_sweep_params(self):
		return self.sweep if self.sweep != [] else None

	# Sweep control layout
	def _gen_sweep_layout(self): 

		self.ctl_layout = QVBoxLayout()

		# Measurement Button. This will be a state machine which 
		# alternates between 'measure' and 'abort' states
		self.meas_state  = QStateMachine()
		self.meas_button = QPushButton()

		self.meas_button.setStyleSheet(
			"background-color: #dddddd; border-style: solid; border-width: 1px; border-color: #aaaaaa; padding: 7px;" )

		# Create measurement states
		self.meas_run  = QState()
		self.meas_stop = QState()

		# Assign state properties and transitions
		self.meas_run.assignProperty(self.meas_button, 'text', 'Abort Sweep')
		self.meas_run.addTransition(self.meas_button.clicked, self.meas_stop)
		self.meas_run.entered.connect(self._exec_sweep_run)

		self.meas_stop.assignProperty(self.meas_button, 'text', 'Measure Sweep')
		self.meas_stop.addTransition(self.meas_button.clicked, self.meas_run)
		self.meas_stop.entered.connect(self._exec_sweep_stop)

		# Add states, set initial state, and state machine
		self.meas_state.addState(self.meas_run)
		self.meas_state.addState(self.meas_stop)
		self.meas_state.setInitialState(self.meas_stop)
		self.meas_state.start()

		# Save traces 
		self.save_button = QPushButton("Save Traces")
		self.save_button.clicked.connect(self._save_traces)	

		# Current/Voltage Sweep Mode 
		self.mode_label = QLabel("Sweep Mode")
		self.mode = QComboBox()
		self.mode.addItems(["Voltage", "Current"])
		self.mode.currentTextChanged.connect(self._update_sweep_control)

		# Sweep Start
		self.start_config={
			"unit" 		: "V",
			"min"		: "u",
			"max"		: "",
			"label"		: "Sweep Start (V)",
			"limit"		: 20.0,
			"signed"	: True,
			"default"	: 0.0
		} 
		self.start = widgets.QUnitSelector.QUnitSelector(self.start_config)

		# Sweep Stop
		self.stop_config={
			"unit" 		: "V",
			"min"		: "u",
			"max"		: "",
			"label"		: "Sweep Start (V)",
			"limit"		: 20.0,
			"signed"	: True,
			"default"	: 1.0
		} 
		self.stop = widgets.QUnitSelector.QUnitSelector(self.stop_config)

		# Compliance Spinbox
		self.cmpl_config={
			"unit" 		: "A", 
			"min"		: "u",
			"max"		: "",
			"label"		: "Compliance (A)",
			"limit"		: 1.0, 
			"signed"	: False,
			"default"	: 0.1
		} 
		self.cmpl = widgets.QUnitSelector.QUnitSelector(self.cmpl_config)	

		# Step Spinbox
		self.npts_label = QLabel("Number of Points")
		self.npts = QSpinBox()
		self.npts.setMinimum(1)
		self.npts.setMaximum(100)
		self.npts.setValue(11)

		# Hysteresis
		self.delay_label = QLabel("Measurement Interval (s)")
		self.delay = QDoubleSpinBox()
		self.delay.setDecimals(3)
		self.delay.setMinimum(0.0)
		self.delay.setMaximum(600.0)
		self.delay.setSingleStep(0.1)
		self.delay.setValue(0.1)

		# Hysteresis
		self.hist = QCheckBox("Hysteresis Mode")

		# Measure button
		self.config_button = QPushButton("Configure Sweep")
		self.config_button.clicked.connect(self._config_sweep_measurement)

		# Measurement Button
		self.ctl_layout.addWidget(self.meas_button)
		self.ctl_layout.addWidget(self.save_button)
		self.ctl_layout.addStretch(1)		

		# Add buttons to box
		self.ctl_layout.addWidget(self.mode_label)
		self.ctl_layout.addWidget(self.mode)
		self.ctl_layout.addWidget(self.start)
		self.ctl_layout.addWidget(self.stop)
		self.ctl_layout.addWidget(self.cmpl)
		self.ctl_layout.addWidget(self.npts_label)
		self.ctl_layout.addWidget(self.npts)
		self.ctl_layout.addWidget(self.delay_label)
		self.ctl_layout.addWidget(self.delay)
		self.ctl_layout.addWidget(self.hist)
		self.ctl_layout.addWidget(self.config_button)

		# Return the layout
		return self.ctl_layout

	# Sweep control dynamic update
	def _update_sweep_control(self):

		# Voltage mode adjust lables and limits
		if self.mode.currentText() == "Voltage":

			# Sweep Start
			self.start_config={
				"unit" 		: "V",
				"min"		: "u",
				"max"		: "",
				"label"		: "Sweep Start (V)",
				"limit"		: 20.0,
				"signed"	: True,
				"default"	: 0.0
			} 
			self.start.update_config(self.start_config)

			# Sweep Stop
			self.stop_config={
				"unit" 		: "V",
				"min"		: "u",
				"max"		: "",
				"label"		: "Sweep Start (V)",
				"limit"		: 20.0,
				"signed"	: True,
				"default"	: 1.0
			} 
			self.stop.update_config(self.stop_config)

			# Compliance Spinbox
			self.cmpl_config={
				"unit" 		: "A", 
				"min"		: "u",
				"max"		: "",
				"label"		: "Compliance (A)",
				"limit"		: 1.0, 
				"signed"	: False,
				"default"	: 0.1
			} 
			self.cmpl.update_config(self.cmpl_config)

		# Current mode adjust lables and limits
		if self.mode.currentText() == "Current":
			
			# Sweep Start
			self.start_config={
				"unit" 		: "A",
				"min"		: "u",
				"max"		: "",
				"label"		: "Sweep Start (A)",
				"limit"		: 1.0,
				"signed"	: True,
				"default"	: 0.0
			} 
			self.start.update_config(self.start_config)

			# Sweep Stop
			self.stop_config={
				"unit" 		: "A",
				"min"		: "u",
				"max"		: "",
				"label"		: "Sweep Stop (A)",
				"limit"		: 1.0,
				"signed"	: True,
				"default"	: 0.1
			} 
			self.stop.update_config(self.stop_config)

			# Compliance Spinbox
			self.cmpl_config={
				"unit" 		: "V", 
				"min"		: "u",
				"max"		: "",
				"label"		: "Compliance (V)",
				"limit"		: 20, 
				"signed"	: False,
				"default"	: 1.0
			} 
			self.cmpl.update_config(self.cmpl_config)

	# Dynamic Plotting Capability
	def _gen_sweep_plot(self): 		

		# Create QDynamicPlot Object
		self.plot = widgets.QDynamicPlot.QDynamicPlot(self)
		self.plot.set_axes_labels("Voltage (V)", "Current (A)")
		self.plot.add_axes()

		# Alias plot layout and return layout
		self.plt_layout = self.plot.layout
		return self.plt_layout

	# Create Measurement 
	def _config_sweep_measurement(self):

		# Enforce data/plot consistency
		if self.plot.hlist == []:
			self._data = []

		# Set up v-source(i-compliance) on keithley 
		if self.mode.currentText() == "Voltage":
			self.keithley.voltage_src()
			self.keithley.current_cmp(self.cmpl.value())

		# Set up i-source(v-compliance) on keithley 
		if self.mode.currentText() == "Current":
			self.keithley.current_src()
			self.keithley.voltage_cmp(self.cmpl.value())

		# Set up measurement object
		self._set_sweep_params(
			self.start.value(), 
			self.stop.value(), 
			self.npts.value(), 
			True if self.hist.checkState()==2 else False)

		# Message box to indicate that sweep variable have been updated
		msg = QMessageBox()
		msg.setIcon(QMessageBox.Information)
		msg.setText("Sweep Parameters Updated")
		msg.setWindowTitle("Sweep Info")
		msg.setStandardButtons(QMessageBox.Ok)
		msg.exec_()


	# Function we run when we enter run state
	def _exec_sweep_run(self):

		# If sweep has been defined		
		if self._get_sweep_params() is not None:

			# For startup protection
			if self.keithley is not None:

				# Update UI button to abort 
				self.meas_button.setStyleSheet(
					"background-color: #ffcccc; border-style: solid; border-width: 1px; border-color: #800000; padding: 7px;")
				self.save_button.setEnabled(False)		

				# Run the measurement thread function
				self.thread = threading.Thread(target=self._exec_sweep_thread, args=())
				self.thread.daemon = True						# Daemonize thread
				self.thread.start()         					# Start the execution
				self.thread_running = True

		# Otherwise show infobox and revert state
		else:
			self.meas_button.click()
			msg = QMessageBox()
			msg.setIcon(QMessageBox.Warning)
			msg.setText("Sweep not configured")
			msg.setWindowTitle("Sweep Info")
			msg.setStandardButtons(QMessageBox.Ok)
			msg.exec_()


	# Function we run when we enter abort state
	def _exec_sweep_stop(self):
		
		# If sweep has been defined		
		if self._get_sweep_params() is not None:
	
			# For startup protection
			if self.keithley is not None:

				# Update UI button to start state
				self.meas_button.setStyleSheet(
					"background-color: #dddddd; border-style: solid; border-width: 1px; border-color: #aaaaaa; padding: 7px;" )
				self.save_button.setEnabled(True)	

				# Kill measurement thread
				self.thread_running = False
				self.thread.join()  # Waits for thread to complete

				# Zero storage arrays
				self._time, self._voltage, self._current = [],[],[]


	# Execute Sweep Measurement
	def _exec_sweep_thread(self):

		# Enforce data/plot consistency
		if self.plot.hlist == []:
			self._data = []


		self._time, self._voltage, self._current = [],[],[]
		handle = self.plot.add_handle()
		start  = time.time()

		# Sweep Voltage Mode
		if self.mode.currentText() == "Voltage":

			# Turn on output and loop through values
			self.keithley.output_on()
			for _v in self._get_sweep_params():

				# If thread is running
				if self.thread_running:

					# Set bias
					self.keithley.set_voltage(_v)

					# Get data from buffer
					_buffer = self.keithley.meas().split(",")

					# Extract data from buffer
					self._time.append(float( time.time() - start ))
					self._voltage.append(float(_buffer[0]))
					self._current.append(float(_buffer[1]))

					# Update plot
					self.plot.update_handle(handle, float(_buffer[0]), float(_buffer[1]))

					# Measurement Interval
					if self.delay.value() != 0: 
						time.sleep(self.delay.value())

				# Else kill output and return
				else:
					self._data.append({ 
						't' : self._time, 
						'V' : self._voltage, 
						'I' : self._current,  
						'P' : np.multiply(self._voltage, self._current)
					})
					self.keithley.set_voltage(0.0)
					self.keithley.output_off()
					return	

		# Sweep Current Mode
		if self.mode.currentText() == "Current":
				
			self.keithley.output_on()
			for _i in self._get_sweep_params():
					
				# If thread is running
				if self.thread_running:

					# Set bias
					self.keithley.set_current(_i)

					# Get data from buffer
					_buffer = self.keithley.meas().split(",")

					# Extract data from buffer
					self._time.append(float( time.time() - start ))
					self._voltage.append(float(_buffer[0]))
					self._current.append(float(_buffer[1]))
		
					# Update plot
					self.plot.update_handle(handle, float(_buffer[0]), float(_buffer[1]))

					# Measurement Interval
					if self.delay.value() != 0: 
						time.sleep(self.delay.value())

				# Else kill output and return
				else:
					self._data.append({ 
						't' : self._time, 
						'V' : self._voltage, 
						'I' : self._current,  
						'P' : np.multiply(self._voltage, self._current)
					})
					self.keithley.set_current(0.0)
					self.keithley.output_off()
					return

		# Zero output after measurement			
		self.keithley.set_voltage(0.0)
		self.keithley.output_off()			
	
		# Append measurement data to data array			
		self._data.append({ 
			't' : self._time, 
			'V' : self._voltage, 
			'I' : self._current,  
			'P' : np.multiply(self._voltage, self._current)
		})
			
		# Update state to stop. We post a button click event to the 
		# QStateMachine to trigger a state transition
		self.meas_button.click()

	# Method to save data traces
	def _save_traces(self):

		# Enforce data/plot consistency
		if self.plot.hlist == []:
			self._data = []

		# Only save if data exists
		if self._data != []:

			dialog = QFileDialog(self)
			dialog.setFileMode(QFileDialog.AnyFile)
			dialog.setViewMode(QFileDialog.Detail)
			filenames = []

			if dialog.exec_():
				filenames = dialog.selectedFiles()
				f = open(filenames[0], 'w+')	

				with f:
				
					for _m in self._data: 

						# Write data header
						f.write("*sweep\n")
						for key in _m.keys():
							f.write("%s\t\t"%str(key))
						f.write("\n")
								
						# Write data values
						for i,_ in enumerate(_m[list(_m.keys())[0]]):
							for key in _m.keys():
								f.write("%s\t"%str(_m[key][i]))
							f.write("\n")

						f.write("\n\n")

				f.close()

			# Message box to indicate successful save
			msg = QMessageBox()
			msg.setIcon(QMessageBox.Information)
			msg.setText("Sweep Data Saved")
			msg.setWindowTitle("Sweep Info")
			msg.setStandardButtons(QMessageBox.Ok)
			msg.exec_()		

		# Warning box in case of no data
		else:		

			msg = QMessageBox()
			msg.setIcon(QMessageBox.Warning)
			msg.setText("No measurement data")
			msg.setWindowTitle("Sweep Info")
			msg.setStandardButtons(QMessageBox.Ok)
			msg.exec_()