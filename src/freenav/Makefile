SM_SOURCES=     flight.sm
SOURCES=        $(SM_SOURCES:%.sm=%_sm.py)

# Uncomment to turn on debug message generation.
TRACE=          -g

# Uncomment to turn on reflection.
# REFLECT=        -reflect

SMC=            Smc.jar
SMC_FLAGS=      -python $(TRACE) $(REFLECT)

RM_F=           rm -f

#################################################################
# Rules.
#

%_sm.py :       %.sm
		$(SMC) $(SMC_FLAGS) $<

%_sm.dot :      %.sm
		$(SMC) -graph -glevel 1 $<

%_sm.png :      %_sm.dot
		dot -T png -o $@ $<

%_sm.html :     %.sm
		$(SMC) -table $<

all :           $(SOURCES)

graph :         $(SM_SOURCES:%.sm=%_sm.dot)

png :           $(SM_SOURCES:%.sm=%_sm.png)

table :         $(SM_SOURCES:%.sm=%_sm.html)

clean :
		-$(RM_F) *_sm.py
		-$(RM_F) *_sm.dot
		-$(RM_F) *_sm.png
		-$(RM_F) *_sm.html
