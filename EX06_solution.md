# EX06 - Displacement of Beam Systems II

This solution follows the same nomenclature used in the professor's notes
(T_z, T_y, M_x, M_t, PVW/PCVW, and z_i along each member).

## 1) Exam 13/06/2023 (3D frame)

**Geometry (mm):**
- A = (0, 1000, 0)
- B = (0, 1000, 1000)
- C = (0, 0, 1000)
- D = (1000, 0, 1000)

**Data:**
- F = 1000 N
- EA = 10^5 N
- EJxx = EJyy = GJ = 10^10 Nmm^2
- l = 1000 mm

We want the displacement **u** at D in the direction of the applied force.

### Hyperstatic choice
Take **R_2A** as the redundant reaction. Use PVW with a unit virtual action
to enforce compatibility (delta = 0 at the released DOF).

### Internal actions (real + virtual)

**Member 1 (A-B):**
- Real: T_z1 = -R_2A
- Virtual 1: T_z1^1 = -1

**Member 2 (B-C):**
- Real: T_y2 = -R_2A,  M_x2 = -R_2A * z2
- Virtual 1: T_y2^1 = -1,  M_x2^1 = -z2
- Virtual 2: unloaded

**Member 3 (C-D):**
- Real: T_y3 = -(R_2A + F),  M_x3 = -(R_2A + F) * z3,  M_t3 = -R_2A * l
- Virtual 1: T_y3^1 = -1,  M_x3^1 = -z3,  M_t3^1 = -l
- Virtual 2: T_y3^2 = -1,  M_x3^2 = -z3,  M_t3^2 = 0

### PVW (compatibility for R_2A)
deltaW_e = 1 * delta = 0

deltaW_i =
  ∫(T_z1^1 T_z1 / EA) dz1
  + ∫(M_x2^1 M_x2 / EJ) dz2
  + ∫(M_x3^1 M_x3 / EJ + M_t3^1 M_t3 / GJ) dz3

= (R_2A l)/EA
  + (R_2A l^3)/(3 EJ)
  + ((R_2A + F) l^3)/(3 EJ)
  + (R_2A l^3)/(GJ)

Solve:
R_2A = -125 N

### PVW (displacement u)
deltaW_e = 1 * u

deltaW_i = ∫(M_x3^2 M_x3 / EJ) dz3
         = (1/EJ) ∫_0^l (R_2A + F) z3^2 dz3
         = (R_2A + F) l^3 / (3 EJ)

u = (R_2A + F) l^3 / (3 EJ)
  = 29.1667 mm

---

## 2) Exam 09/09/2024 (truss)

**Geometry:** isosceles truss with two inclined bars (length l) and one
vertical bar (length l). With symmetry, theta = 30 deg.

**Data:**
- l = 1000 mm
- EA = 10^8 N
- F = 1000 N

All members are truss bars: only axial forces.

### Internal actions (real)
T1 * cos(theta) = F/2  ->  T1 = F / (2 cos(theta)) = F / sqrt(3)
T2 = T1 * sin(theta)   ->  T2 = F / (2 sqrt(3))

### Virtual system (unit load along u)
T1^1 * cos(theta) = 1/2  ->  T1^1 = 1 / sqrt(3)
T2^1 = T1^1 * sin(theta) ->  T2^1 = 1 / (2 sqrt(3))

### PCVW
deltaW_e = 1 * u

deltaW_i =
  2 * (1/EA) ∫_0^l (T1^1 T1) dz1
  + (1/EA) ∫_0^l (T2^1 T2) dz2

= 2 * (1/EA) ∫_0^l (F/3) dz1 + (1/EA) ∫_0^l (F/12) dz2
= 2 F l / (3 EA) + F l / (12 EA)
= 3 F l / (4 EA)

u = 3 F l / (4 EA) = 0.0075 mm
