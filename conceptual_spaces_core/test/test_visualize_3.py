from intvalpy import lineqs
import numpy as np
import matplotlib.pyplot as plt

A = -np.array([[-0.894, -0.447],
               [0, -1],
               [0, 1],
               [1, 0],
               [0.894, 0.447]])
b = -np.array([-0.671, 0, 1, 1, 1.073])

vertices = lineqs(A, b, show=False)
fig = plt.figure(figsize=(15, 15))
ax = fig.add_subplot(111, title='Solution')
x, y = vertices[:, 0], vertices[:, 1]
ax.fill(x, y, linestyle='-', linewidth=1, color='red', alpha=0.2)
ax.scatter(x, y, s=10, color='black', alpha=1)
plt.show()