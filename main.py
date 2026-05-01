# # Please install OpenAI SDK first: `pip3 install openai`
# import os
# from openai import OpenAI

# client = OpenAI(
#     api_key="sk-8983de8f57c04b8bbaaedfccfb6b637b",
#     base_url="https://api.deepseek.com")

# response = client.chat.completions.create(
#     model="deepseek-chat",
#     messages=[
#         {"role": "system", "content": "You are a helpful assistant"},
#         {"role": "user", "content": "Hello"},
#     ],
#     stream=False
# )

# print(response.choices[0].message.content)


import numpy as np

def sigmoid(z):
    return 1 / (1 + np.exp(-z))

def gru_cell(x: np.ndarray, h_prev: np.ndarray,
             W_z: np.ndarray, U_z: np.ndarray, b_z: np.ndarray,
             W_r: np.ndarray, U_r: np.ndarray, b_r: np.ndarray,
             W_h: np.ndarray, U_h: np.ndarray, b_h: np.ndarray) -> np.ndarray:
    """
    Implements a single GRU cell forward pass.
    
    Args:
        x: Input vector of shape (input_size,)
        h_prev: Previous hidden state of shape (hidden_size,)
        W_z, W_r, W_h: Weight matrices for input
        U_z, U_r, U_h: Weight matrices for hidden state
        b_z, b_r, b_h: Bias vectors
        
    Returns:
        h_next: New hidden state of shape (hidden_size,)
    """
    rt = sigmoid(W_r @ x + U_r @ h_prev + b_r)
    zt = sigmoid(W_z @ x + U_z @ h_prev + b_z)
    h_hat_t = sigmoid(W_h @ x + U_h @ (rt * h_prev) + b_h)
    ht = zt * h_prev + (1 - zt) * h_hat_t
    return ht


x = np.array([1.0, 0.5])
h_prev = np.zeros(3)
W_z = np.ones((3, 2)) * 0.1
U_z = np.ones((3, 3)) * 0.1
b_z = np.zeros(3)
W_r = np.ones((3, 2)) * 0.1
U_r = np.ones((3, 3)) * 0.1
b_r = np.zeros(3)
W_h = np.ones((3, 2)) * 0.2
U_h = np.ones((3, 3)) * 0.2
b_h = np.zeros(3)
result = gru_cell(x, h_prev, W_z, U_z, b_z, W_r, U_r, b_r, W_h, U_h, b_h)
print(np.round(result, 4))