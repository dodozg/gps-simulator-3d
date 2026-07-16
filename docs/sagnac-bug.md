# The Sagnac bug: a 25-meter lie hidden in the noise

*A short engineering story from GPS Simulator 3D. It's a good one because the bug
was invisible for as long as the simulator was noisy, and it took a specific
diagnostic trick to expose — the kind of trick that generalizes.*

## The symptom

The receiver worked. Across five continents it converged to a position with a
median error of ~50 m — plausible for a noisy single-point fix, so nobody looked
closer. The error *looked* like honest measurement noise: it jittered, it had no
obvious pattern, and it sat comfortably inside what the multipath and thermal
models could explain.

That last part is the trap. When your noise budget is large enough to explain a
bias, the bias hides inside it.

## The tightening

The story only started when I set out to push the accuracy down toward
single-digit meters. Two fixes removed most of the *random* error:

1. **Correlation quantization.** The pseudorange was measured by correlating a
   PRN code sampled at one sample per chip (~293 m). Parabolic peak
   interpolation recovered only ~0.1 chip (~27 m) — the dominant, hidden error
   floor. Oversampling the correlation 8× dropped ranging to ~2.5 m.
2. **Thermal-noise pessimism.** The de-spread SNR was set to −10 dB; at that
   level thermal noise dominated the ranging. Raising it to a realistic −2 dB
   let the code phase settle.

With the *random* error cut down, something that had been submerged surfaced: a
**persistent** offset. The median stopped improving and a residual just sat
there, refusing to average away no matter how many epochs ran.

## The diagnosis: decompose the error, don't stare at its magnitude

The magnitude of a position error tells you almost nothing about its cause. Its
**direction** tells you a lot. So I stopped looking at ‖error‖ and projected the
error vector into the local **East / North / Up** frame at the receiver, epoch by
epoch, and averaged.

The signature was unmistakable: the East mean was ~+25 m and stable, while North
and Up averaged to ~zero. A bias that lives almost entirely on **one horizontal
axis, fixed in the Earth frame,** is not multipath and not thermal noise — those
are zero-mean and isotropic. Something in the model was systematically pulling
the solution east.

An east-only, Earth-fixed bias points at one suspect: the **Sagnac effect** — the
correction for the Earth rotating underneath the signal during its ~70 ms flight.
Sagnac is antisymmetric in the equatorial plane and, for a mid-latitude
receiver, projects predominantly onto the east axis. The fingerprint matched the
suspect.

## The root cause: corrected, but never injected

Here is the actual bug, and it is embarrassingly simple once you see it.

The **receiver's measurement model** included the Sagnac term. When it predicted
the pseudorange for a satellite, it added the Sagnac correction:

```python
h_x = range_est + clock + sagnac + isb        # model: Sagnac IS here
```

But the **simulated measurement** — the pseudorange the channel actually produced
— never had Sagnac in it. The signal-propagation model computed a plain
geometric range and skipped the term entirely.

So the receiver was *correcting for an effect that was never in the data.* Every
epoch it subtracted a ~25 m east-projected quantity that the measurement didn't
contain, and dutifully shifted its position east to make the books balance. The
filter wasn't broken; it was faithfully solving a rigged equation.

The fix is one line — add the term to the measurement so injection and correction
finally agree:

```python
iono_free_pr += calculate_sagnac_correction(sig['pos'], self.pos)
```

Result: the east bias vanished, the error became unbiased (ENU means ~±1 m), and
the median dropped to ~4–5 m.

## The real lesson: noise is a hiding place

The uncomfortable part isn't the missing line — it's that the bug lived for a
long time and was *actively masked by the project's own imperfections.* As long
as multipath and thermal noise were large, a 25 m coherent bias looked like a
slightly unlucky draw. Improving the random error is what made the systematic
error visible. **Fixing one class of error can reveal another that was always
there.**

This is a whole *class* of bug: the model corrects for something the measurement
doesn't contain, or vice versa. It is silent by construction, because a
zero-mean noise floor will always partially explain a bias. You cannot catch it
by looking at accuracy numbers — they look fine.

So the durable fix isn't the Sagnac line. It's a test that removes the hiding
place:

## The guard: a zero-noise consistency test

Turn **every** stochastic and quantization error off — multipath, thermal noise,
correlator quantization (replace it with a perfect ranging device), ephemeris
error, clock noise. What remains is only the deterministic models that the
receiver also corrects for: geometry, troposphere, Sagnac, ionosphere,
inter-system bias, relativity.

If every injected term is *exactly* cancelled by its correction, the position
error must collapse to machine precision. It does: across five locations the
residual falls to **~10 µm**. Any missing or spurious term — a re-introduced
Sagnac mismatch, a sign error, a frame confusion — would push that residual from
microns to **meters**, and the test fails loudly, with no noise to hide behind.

```
Zagreb / London / Equator / Tokyo / Anchorage :  ~0.00001 m  (machine precision)
```

That test (`tests/test_consistency.py`) is now the real deliverable of this
story. The Sagnac fix closed one hole; the zero-noise test closes the whole
category the hole belonged to.

## Takeaways

- **Decompose errors into a meaningful basis** (here, ENU). A bias's *direction*
  and *stability* identify its cause; its magnitude rarely does.
- **A coherent, one-axis, frame-fixed bias is a model inconsistency,** not noise.
- **Injection and correction must be symmetric.** If the estimator models a term,
  the measurement must contain it — and vice versa.
- **Reducing random error can unmask systematic error.** Budget your noise
  honestly, or it will explain your bugs for you.
- **Test at zero noise.** It's the cheapest guard against the most expensive
  class of GNSS bug.

---

*See also: [technical documentation §7 (the 50 m → 5 m case study)](../GPS_Simulator_Documentation.md)
and the [English README](../README.en.md).*
