import numpy as np
import matplotlib.pyplot as plt

N = 11
GAMMA = 0.95
ALPHA = 0.3
MAX_ITER = 300

# 奖励
R = np.array([3.0] + [-1.0] * 4 + [0.0] + [1.0] * 5)

# 转移概率
P = np.zeros((N, N, 2))
for s in range(N):
    P[max(0, s - 1), s, 0] = 0.7;
    P[min(10, s + 1), s, 0] = 0.3
    P[max(0, s - 1), s, 1] = 0.3;
    P[min(10, s + 1), s, 1] = 0.7

# 真实 V* (最优策略: 始终向左)
P_opt = P[:, :, 0]
V_star = np.linalg.solve(np.eye(N) - GAMMA * P_opt, R)


def eval_pi(Q):
    pi = np.argmax(Q, axis=1)
    P_pi = np.column_stack([P[:, s, pi[s]] for s in range(N)])
    V = np.zeros(N)
    for _ in range(500):
        V_new = R + GAMMA * P_pi @ V
        if np.max(np.abs(V_new - V)) < 1e-9: break
        V = V_new
    return V


np.random.seed(42)
Q_b = 0.1 * np.random.randn(N, 2)  # 用正态分布，有正有负
Q_a = 0.1 * np.random.randn(N, 2)

err_b, gap_b = [], []
err_a, gap_a = [], []

# 打印前5次迭代的详细Q值，验证"向左/向右"的体现
print("迭代过程抽样 (状态0, 5, 10 的 Q 值):")
print(f"{'Iter':<4} {'Method':<12} {'s0(L/R)':<12} {'s5(L/R)':<12} {'s10(L/R)':<12} {'Policy(s0)':<8}")

for k in range(MAX_ITER):
    # === Bellman 更新 ===
    V_pi_b = eval_pi(Q_b)
    err_b.append(np.max(np.abs(V_star - V_pi_b)))
    gap_b.append(np.mean(Q_b[:, 0] - Q_b[:, 1]))

    V_max_b = np.max(Q_b, axis=1)
    Q_new_b = np.zeros_like(Q_b)
    for s in range(N):
        for a in range(2):
            Q_new_b[s, a] = R[s] + GAMMA * np.dot(P[:, s, a], V_max_b)
    Q_b = Q_new_b

    # === Advantage Learning 更新 ===
    V_pi_a = eval_pi(Q_a)
    err_a.append(np.max(np.abs(V_star - V_pi_a)))
    gap_a.append(np.mean(Q_a[:, 0] - Q_a[:, 1]))

    V_max_a = np.max(Q_a, axis=1)
    Q_new_a = np.zeros_like(Q_a)
    for s in range(N):
        for a in range(2):
            # 优势项: α * (Q(s,a) - max_a' Q(s,a'))
            advantage = ALPHA * (Q_a[s, a] - np.max(Q_a[s, :]))
            Q_new_a[s, a] = R[s] + advantage + GAMMA * np.dot(P[:, s, a], V_max_a)
    Q_a = Q_new_a

    # 打印前5次迭代的抽样
    if k < 5:
        pi0_b = 'L' if np.argmax(Q_b[0]) == 0 else 'R'
        print(
            f"{k:<4} {'Bellman':<12} {Q_b[0, 0]:6.3f}/{Q_b[0, 1]:6.3f}   {Q_b[5, 0]:6.3f}/{Q_b[5, 1]:6.3f}   {Q_b[10, 0]:6.3f}/{Q_b[10, 1]:6.3f}   {pi0_b:<8}")
        pi0_a = 'L' if np.argmax(Q_a[0]) == 0 else 'R'
        print(
            f"{k:<4} {'Adv-Learn':<12} {Q_a[0, 0]:6.3f}/{Q_a[0, 1]:6.3f}   {Q_a[5, 0]:6.3f}/{Q_a[5, 1]:6.3f}   {Q_a[10, 0]:6.3f}/{Q_a[10, 1]:6.3f}   {pi0_a:<8}")

# 绘图 - 每个点都标记，避免"就画了几个点"的误解
iters = np.arange(MAX_ITER)
plt.figure(figsize=(9, 10))

# 图1: 性能界 (每个点都画标记)
plt.subplot(2, 1, 1)
plt.semilogy(iters, err_b, 'b-o', markersize=2, markevery=10, label='Bellman', linewidth=1)
plt.semilogy(iters, err_a, 'r-s', markersize=2, markevery=10, label='Advantage Learning', linewidth=1)
plt.ylabel(r'$\|V^* - V^{\pi_k}\|_\infty$')
plt.title('Policy Performance Bound')
plt.legend();
plt.grid(True, alpha=0.3)

# 图2: Action Gap (每个点都画标记)
plt.subplot(2, 1, 2)
plt.plot(iters, gap_b, 'b-o', markersize=2, markevery=10, label='Bellman', linewidth=1)
plt.plot(iters, gap_a, 'r-s', markersize=2, markevery=10, label='Advantage Learning', linewidth=1)
plt.axhline(0, color='k', ls='--', linewidth=0.5)
plt.xlabel('Iteration k')
plt.ylabel('Action Gap = mean_s[Q(s,L) - Q(s,R)]')
plt.title('Action Gap Evolution')
plt.legend();
plt.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('chainwalk_dp_detailed.png', dpi=300)
plt.show()

# 最终验证: 输出最后一次的策略和Action Gap
print(f"\n最终结果 (Iter={MAX_ITER - 1}):")
print(f"Bellman  - Action Gap: {gap_b[-1]:.4f}, 策略(s0): {'L' if np.argmax(Q_b[0]) == 0 else 'R'}")
print(f"Adv-Learn- Action Gap: {gap_a[-1]:.4f}, 策略(s0): {'L' if np.argmax(Q_a[0]) == 0 else 'R'}")
print(f"理论最优: Action Gap 应为正(因最优策略是始终向左)")