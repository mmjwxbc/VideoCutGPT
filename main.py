import numpy as np

def linear_regression_gradient_descent(X: np.ndarray, y: np.ndarray, alpha: float, iterations: int) -> np.ndarray:
    """
    Perform linear regression using gradient descent.

    Args:
        X: Feature matrix of shape (m, n) where first column is all ones (for intercept)
        y: Target vector of shape (m,)
        alpha: Learning rate
        iterations: Number of gradient descent iterations
    
    Returns:
        Learned weights as a 1D array of shape (n,)
    """
    m, n = X.shape
    y = y.reshape(-1, 1)  # Ensure y is a column vector
    theta = np.zeros((n, 1))  # Initialize weights to zeros
    W = np.zeros((n, 1))
    b = 0
    for _ in range(iterations):
        h = X @ W + b
        error = 1 / (2 * m) * (h - y).T @ (h - y)
        grad_w = 1 / m * (h - y) * X # (m,) (m)
        grad_b = 1 / m * (h - y).sum()
        W -= alpha * grad_w
        b -= alpha * grad_b
    # Your code here: implement gradient descent

    return W.flatten()

print(np.round(linear_regression_gradient_descent(np.array([[1, 1], [1, 2], [1, 3]]), np.array([3, 5, 7]), 0.1, 1000), 4))