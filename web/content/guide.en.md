# GPS Simulator 3D — explained like you're 13

Imagine you want to build a **virtual GPS system inside a computer**.

In that virtual world there are:

* satellites orbiting the Earth
* a GPS receiver on the ground, for example a phone or a car
* radio signals travelling from the satellites to the receiver
* an atmosphere that slows the signals down a little
* mountains that can block satellites
* errors in the clocks and in the satellite positions
* a program that tries to work out where the receiver is from all of that

That is what **GPS Simulator 3D** does.

It is not just an animation of satellites. Behind the 3D view sits a real mathematical system that tries to solve the same basic problem a GPS receiver in your phone solves.

## 1. The simplest picture of the whole project

We can picture the project as a car.

### The engine is the motor

The Python program computes:

* where the satellites are
* how they move
* how long the signal travels
* what errors arise
* where the receiver most likely is

The motor can run without any graphics.

### Web and desktop are the dashboard

They display the motor's results:

* the web version shows the Earth and satellites in a browser
* the desktop version shows a 3D scene in a separate application
* the CLI tools run specific experiments with no graphical interface

In other words:

> The engine thinks and computes, and the interfaces show what is happening.

## 2. How does GPS even know where you are?

Every satellite constantly sends a message that roughly says:

> I am satellite number 12. I am here right now. I sent this message at exactly this time.

The GPS receiver measures how long the message travelled.

Because a radio signal travels at roughly the speed of light, the distance can be computed:

```text
distance = speed of light × travel time
```

If you know the distance to one satellite, you only know that you are somewhere on a big sphere around it.

With two satellites you get a narrower set of possible positions. With three you can roughly pin down a position.

In practice at least **four satellites** are needed, because the receiver has to compute:

1. the east–west position
2. the north–south position
3. the altitude
4. the error of its own clock

The receiver in the simulator usually uses more satellites so the result is more stable.

## 3. What do the individual parts of the simulator do?

### physics_engine.py — the physics teacher

This module computes the physical phenomena: satellite motion, gravitational effects, the slowing of signals in the atmosphere, the Earth's rotation, clock errors and relativistic effects.

Relativity sounds like something out of science fiction, but GPS really has to account for it. Satellite clocks do not tick at exactly the same rate as clocks on Earth.

### satellite.py — the satellite manager

This part creates and organises the satellites. It can simulate four systems:

* **GPS** — American
* **Galileo** — European
* **GLONASS** — Russian
* **BeiDou** — Chinese

With all of them on, the simulator can have about **96 satellites**. Of course, the receiver does not see all 96 at once — many are on the other side of the Earth at that moment, or too low above the horizon.

### signal_processing.py — the virtual antenna and radio

This module tries to mimic receiving a GPS signal. Every satellite has a special digital pattern called a **PRN code**. Think of it as a special rhythm:

```text
satellite 1: + - + + - - + ...
satellite 2: - + - - + + - ...
```

The receiver knows those patterns. In the received noise it looks for the moment where its own local pattern best matches the signal. This is called **correlation**, and it is similar to trying to recognise a familiar melody in a noisy room.

The simulator checks the signal eight times more finely than before, so it can pin down the arrival time of the signal — and therefore the distance to the satellite — more precisely.

### terrain.py — the relief map

This part knows where the mountains, valleys and hills are, and how high the ground actually is. If a mountain sits between the receiver and a satellite, the signal can be blocked. So the simulator does not only check whether a satellite is above the horizon, but also whether there is a real, unobstructed line between the receiver and the satellite.

### receiver.py — the virtual GPS receiver

This is the main part of the project. It:

1. finds the visible satellites
2. picks the useful ones
3. processes their signals
4. corrects the known errors
5. computes the position
6. checks whether any satellite is sending unusual data

It is the "brain" of the whole simulator.

## 4. What does one round of the simulation look like?

The web application repeats this process about **10 times per second**:

1. The satellites move along their orbits.
2. It works out which satellites are visible.
3. Each visible satellite sends a virtual signal.
4. Noise and physical errors are added to the signal.
5. The receiver measures the distances.
6. A mathematical filter estimates the position.
7. The system checks for suspicious measurements.
8. The new result is sent to the browser.
9. Cesium refreshes the globe, the satellites and the charts.

All of this happens fast enough to look like a live simulation.

## 5. Why isn't a GPS measurement perfect?

The signal does not travel through ideal, empty space.

### The ionosphere

A high layer of the atmosphere with electrically charged particles slows the signal down. Different radio frequencies are slowed by different amounts, so the receiver can compare signals on two frequencies, L1 and L2, and remove a large part of the ionospheric error. This is the **iono-free combination**. The downside is that it amplifies part of the ordinary noise.

### The troposphere

The lower part of the atmosphere, where we live and where clouds form, also slows the signal down. Unlike the ionosphere, this error cannot be removed by comparing L1 and L2, so the simulator uses a mathematical model of the atmosphere.

### Multipath

The signal can bounce off a building, the ground, a rock or a metal surface. The receiver then gets a direct signal plus one or more delayed copies. It is like an echo: if you shout in a tunnel, you hear your original voice and its echoes. Because of this the GPS receiver may think the signal travelled a little further than it really did.

### Noise

Radio signals are extremely weak, and the electronics and the environment create random interference. So the simulator adds **AWGN**, a kind of mathematically modelled white noise.

### Satellite position error

The receiver does not know exactly where a satellite is — it uses the orbit data the satellite broadcasts. That data can contain a small error. In the simulator this error changes slowly, because real satellite orbit errors do not jump around completely at random every tenth of a second either.

### The Sagnac effect

While the signal travels from the satellite to the receiver, the Earth keeps rotating. The signal travels for only a fraction of a second, but GPS tries to measure position in metres, so even such a tiny rotation of the Earth matters. If this effect is applied incorrectly, the computed position can be shifted by tens of metres.

## 6. What is the EKF?

EKF stands for **Extended Kalman Filter**.

Imagine you are tracking a cyclist you cannot see clearly all the time. At one moment you know where they were, how fast they were going and in which direction, so you can predict where they should be a second later. When you get a new, slightly inaccurate measurement, you compare it with the prediction.

The Kalman filter constantly combines **what it expects** with **what it just measured**, and it does not fully trust either one.

The simulator's filter tracks **11 values**:

* 3 position values
* 3 velocity values
* the clock error
* the change of the clock error
* 3 differences between the time systems of Galileo, GLONASS and BeiDou

### How does it start if it knows nothing yet?

At the start the simulator uses the **least squares** method for a first rough position estimate. After that the EKF takes over the tracking and gradually improves the estimate.

> Least squares finds the initial position, and the EKF then tracks and smooths it.

## 7. What is RAIM?

RAIM is a system that checks whether the satellite measurements agree with each other.

Imagine five friends trying to guess how far away the school is:

* the first says 800 m
* the second says 810 m
* the third says 790 m
* the fourth says 805 m
* the fifth says 6 km

The fifth answer clearly looks suspicious. RAIM does something similar: it looks for a satellite whose measurement differs greatly from the others and can throw it out of the calculation.

But RAIM has an important limitation. If **all the satellite signals together tell the same, well-coordinated lie**, RAIM may not realise anything is wrong — all the measurements agree with each other, even though they lead to the wrong place. That is not a flaw of this simulator, but a real limitation of this kind of protection.

## 8. Why doesn't the simulator always use all the satellites?

More satellites usually helps, but not every satellite is equally useful. A satellite high in the sky usually gives a better signal, while a satellite very low above the horizon has a longer path through the atmosphere and more often causes reflection problems.

So the simulator picks up to ten satellites that give good geometry. Good geometry means the satellites are nicely spread across the sky, not crammed into the same direction.

### GDOP

**GDOP** is a number that describes how good the satellite arrangement is: a smaller GDOP means better geometry, a larger one means worse. Imagine trying to find the intersection point of several lines — if they all come from almost the same direction, a small error can shift the result a lot; if they come from different directions, the position is easier to determine.

## 9. What is ISB?

GPS, Galileo, GLONASS and BeiDou do not use exactly the same time scale. This creates small differences in the measured distances, called **inter-system bias** (ISB).

For example, a signal from one system may look as though it travelled a few metres more or less, even though the real reason is the difference between the systems' clocks. The simulator deliberately adds these differences, and the EKF then tries to estimate them — so it does not pretend all the systems are perfectly synchronised.

## 10. What do NIS and DOP mean?

### NIS — is the filter realistic?

NIS checks whether the actual errors match what the filter expects. Very simply:

* NIS around 1: the filter estimates how noisy the measurements are well
* consistently above 1: the filter is overconfident
* consistently below 1: the filter is overly cautious

It is like a student estimating how much they know before a test: if they expect an A but keep getting a D, they are overconfident; if they expect a D but keep getting an A, they are overly cautious.

### DOP — how good is the satellite arrangement?

DOP tells you how much the satellite geometry will amplify the measurement errors. Even with good-quality signals, a poor satellite arrangement can give a poor position.

## 11. How accurate is the simulator?

The project used to have an error of about **50 metres**. After many fixes it came down to roughly:

* a typical error: **4–6 metres**
* in most harder cases: **6–10 metres**
* occasional peaks: about **12–15 metres**

That is realistic for classic satellite positioning without a special ground correction station. It is not a centimetre-precision system like advanced RTK.

## 12. How was the error reduced from 50 to about 5 metres?

This is one of the most interesting parts of the project.

### Problem 1: signal measurement too coarse

The earlier signal processing could tell distances apart only to within about 27 metres. The solution was to sample the signal eight times more finely and to locate the correlation peak more precisely, which brought the measurement error down to about a few metres.

### Problem 2: the Sagnac correction was inconsistent

The receiver tried to remove the Earth's rotation, but that phenomenon had not been properly added to the simulated measurement. It was like a calculator subtracting 25 when nobody had added 25 in the first place. The result was a shift towards the east of about 25 metres. Once the model was fixed on both sides, the error disappeared.

### Problem 3: the troposphere was not corrected

The ionospheric correction does not remove the tropospheric error, so a separate model for the troposphere was added.

### Problem 4: too much radio noise

The old parameters assumed too much noise, so they were set to a more realistic level.

### Problem 5: the filter judged measurement quality incorrectly

The Kalman filter's parameters were tuned so that its NIS is about 1, which means the filter started estimating its own uncertainty more accurately.

## 13. Why did some more-realistic changes make the result worse?

This is important to understand:

> A more realistic simulator does not always produce nicer results.

If you artificially make all errors completely random, the Kalman filter can easily average them out. But some real errors last a long time and do not vanish under a simple average.

When a more realistic model of the satellite orbit error was introduced, the position error rose in places, for example from about 4.5 to 5.6 metres. That is not a fault — the old model was simply too optimistic.

It is like a video game: you can turn off the wind and rain and driving becomes easier; if you turn them on, the result can be worse, but the simulation becomes more real.

## 14. What does the web application show?

The web application is the control centre of the simulator. In it you can:

* view the Earth in 3D
* track the satellites and their orbits
* see which satellites are on
* turn GPS, Galileo, GLONASS and BeiDou on and off
* move the receiver
* speed time up or pause it
* turn RAIM on and off
* track the position error, GDOP and NIS
* run experiments and go through guided lessons
* change the parameters of an individual satellite
* simulate faults and interference

The backend computes the simulation, and the frontend shows the results on the globe. They are connected by a WebSocket, which means the connection stays open and the server keeps sending new states without reloading the page.

## 15. How "real" is the project, and how simplified?

### The real and serious parts

The project genuinely uses: orbit computation, correction of atmospheric errors, the Sagnac effect, satellite and receiver clocks, PRN signal processing, position solving, an 11-state Kalman filter, RAIM, working with multiple GNSS systems, the differences between their time scales, a real terrain model and statistical quality checks. These are not just pre-drawn animations.

### The simplified parts

The signal layer is not yet fully equal to a real GPS receiver:

* the PRN codes are not real GPS Gold codes
* there is no full Doppler-shift model
* there is no real carrier-phase tracking
* there is no full decoding of navigation messages
* there is no real input from an antenna
* some parameters are tuned to give realistic results, but are not derived from the entire physical radio link

So the best description is:

> The mathematical and navigation part is very serious, while the radio signal is still simplified.

## 16. Could it work with real GPS data?

A large part of it could. Right now the simulator produces virtual measurements itself. To work with a real GPS receiver, you would need to add a part that reads raw measured distances, data from RINEX files, data from a real GNSS device, real satellite orbit data and satellite clock corrections.

After that the existing solver could try to compute the real position. But for centimetre precision you would need to add **carrier-phase** processing and a full RTK system.

## 17. How does the project check that nothing is broken?

The project has about **60 automated tests**. They check coordinate conversion, satellite positions, signal processing, position solving, RAIM, terrain, spoofing experiments, the web backend and the statistical behaviour of the filter.

The **zero-noise test** is especially important. In it, noise, multipath, orbit errors, clock errors and measurement errors are turned off. If all the physical models and corrections match perfectly, the result must be almost exactly correct. If an error of a few metres appears, it means some effect was:

* added but not removed
* removed but never added
* computed differently in the measurement and in the receiver

This is the best way to find silent bugs like the old Sagnac problem.

## 18. What are the project's biggest strengths?

1. **It is not just a pretty animation** — the 3D view is only the outer layer; behind it a real navigation algorithm actually runs.
2. **It shows why GPS goes wrong** — the effect of the atmosphere, poor satellite arrangement, reflections, satellite faults, inaccurate clocks and different GNSS systems.
3. **It is good for learning** — instead of just reading the definition of GDOP or RAIM, you can change the conditions and see the result immediately.
4. **It is well tested** — automated tests reduce the chance that a new change silently breaks existing functionality.
5. **It honestly describes its simplifications** — the documentation does not claim that every part is a perfect copy of a real GPS receiver.

## 19. What are the biggest weaknesses?

### The signal layer is not fully realistic

For a true software GPS receiver, the radio signal would need to be simulated in much more detail.

### receiver.py does too many things

A single file handles channel processing, corrections, satellite selection, the EKF and RAIM. It would be clearer to split it into several smaller parts.

### There are two graphical interfaces

The desktop and web versions partly do the same thing, which in the long run means double maintenance. The web version looks like the more logical direction of development.

### The project lives on Google Drive

This causes technical problems with large numbers of small files, especially with `node_modules`. It would be better to keep the active repository on a local SSD and use Git for synchronisation and backup.

## 20. The final verdict in simple words

This project is much more than a school demonstration of satellites. It is best described as:

> A virtual GPS laboratory in which the computer plays the satellites, the atmosphere, the radio channel and the receiver.

Its strongest part is not the 3D graphics, but the fact that it creates imperfect measurements, tries to correct them with real algorithms, estimates its own uncertainty, recognises some faulty measurements, and lets you watch the whole process live.

A score of **8/10** makes sense: as a learning tool it is excellent, as a research laboratory it is very good, and as a real GPS receiver it has a strong core but still lacks a real antenna input and a more complete signal layer.

### In one sentence

**GPS Simulator 3D is like a very advanced video game for GPS: the satellites, the atmosphere and the errors are simulated inside a computer, and a real mathematical "GPS brain" tries to find the position from noisy signals to within a few metres.**
