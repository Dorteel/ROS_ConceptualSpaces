import numpy as np
import matplotlib.pyplot as plt
from sympy.solvers import solve
from sympy import Symbol

def f1(x):
    return (-0.894*x+0.671)/0.447
def f2(x):
    return (1*x+0.5)/1
def f3(x):
    return (1*x-1)/-1
def f4(x):
    return (x-1)/0
def f5(x):
    return (0.894*x-1.073)/-0.447

x = Symbol('x')
x1, =  solve(f1(x)-f2(x))
x2, =  solve(f1(x)-f3(x))
x3, =  solve(f2(x)-f3(x))

y1 = f1(x1)
y2 = f1(x2)
y3 = f2(x3)
print(x1, y1)
plt.plot(x1,f1(x1),'go',markersize=10)
plt.plot(x2,f1(x2),'go',markersize=10)
plt.plot(x3,f2(x3),'go',markersize=10)

plt.fill([x1,x2,x3,x1],[y1,y2,y3,y1],'red',alpha=0.5)

xr = np.linspace(0,1,100)
y1r = f1(xr)
y2r = f2(xr)
y3r = f3(xr)

plt.plot(xr,y1r,'k--')
plt.plot(xr,y2r,'k--')
plt.plot(xr,y3r,'k--')

plt.xlim(0,1)
plt.ylim(0,1)

plt.show()