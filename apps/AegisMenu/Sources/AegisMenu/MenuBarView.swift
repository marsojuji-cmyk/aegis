import AppKit
import SwiftUI

struct MenuBarView: View {
    @EnvironmentObject private var store: AegisStore
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().padding(.vertical, 6)
            metrics
            Divider().padding(.vertical, 6)
            controls
            Divider().padding(.vertical, 6)
            footer
        }
        .padding(12)
        .frame(width: 320)
    }

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: store.menuIcon)
                .font(.title2)
                .foregroundStyle(store.signalColor)
                .symbolRenderingMode(.hierarchical)
            VStack(alignment: .leading, spacing: 2) {
                Text("Aegis")
                    .font(.headline)
                Text(store.isHealthy ? "Router online" : "Router offline")
                    .font(.caption)
                    .foregroundStyle(store.isHealthy ? Color.secondary : Color.red)
            }
            Spacer()
            if store.isBusy {
                ProgressView().controlSize(.small)
            }
        }
    }

    private var metrics: some View {
        VStack(alignment: .leading, spacing: 8) {
            metricRow(
                "Reserve",
                value: store.reserveSignal.uppercased(),
                color: store.signalColor
            )
            metricRow(
                "Capacity left",
                value: String(format: "%.1f%%", store.remainingPct)
            )
            if let saved = store.budget?.totalTokensSaved {
                metricRow("Tokens saved (week)", value: formatInt(saved))
            }
            if let consumed = store.budget?.totalTokensConsumed {
                metricRow("Tokens used (week)", value: formatInt(consumed))
            }
            if let reuse = store.budget?.reuseHitRatePercent ?? store.status?.reuseHitRatePercent {
                metricRow("Reuse hit rate", value: String(format: "%.1f%%", reuse))
            }
            if let credits = store.surplus?.availableCredits {
                metricRow("Surplus credits", value: formatInt(credits))
            }
            if let proj = store.forecast?.projectedSignal {
                metricRow(
                    "Week forecast",
                    value: proj.uppercased(),
                    color: proj == "ok" ? .green : (proj == "throttle" ? .orange : .red)
                )
            }
            if let burn = store.forecast?.avgDailyBurn,
               let safe = store.forecast?.recommendedDailyBudget {
                metricRow(
                    "Burn / safe",
                    value: "\(Int(burn))/\(Int(safe))",
                    color: (store.forecast?.burnWarning?.active == true) ? .orange : .primary
                )
            }
            if let hit = store.intel?.cacheHitRatePercent {
                metricRow("Cache hit", value: String(format: "%.1f%%", hit))
            }
            if let ticks = store.intel?.state?.ticks {
                metricRow("Intel ticks", value: "\(ticks)")
            }
            if let ba = store.intel?.budgetAware, let band = ba.band, band != "ok" {
                metricRow(
                    "Budget",
                    value: band.uppercased(),
                    color: band == "emergency" ? .red : (band == "adaptive" ? .orange : .yellow)
                )
            }
            if let pid = store.status?.daemon?.pid {
                metricRow("PID", value: "\(pid)")
            }
            if let ba = store.intel?.budgetAware, ba.band != nil, ba.band != "ok" {
                Text(ba.menuSummary ?? "Budget adaptive")
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .lineLimit(3)
                if let shed = ba.modulesShed, !shed.isEmpty {
                    Text("Shed: \(shed.prefix(4).joined(separator: ", "))")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            if let bs = store.forecast?.burnStatus, let level = bs.level, level != "ok" {
                let color: Color = level == "critical" ? .red : (level == "warn" ? .orange : .yellow)
                Text("[\(level.uppercased())] \(bs.message ?? "")")
                    .font(.caption2)
                    .foregroundStyle(color)
                    .lineLimit(4)
                Text(bs.fixDetail ?? "Cut fan-out if burn stays high")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(color)
            } else if store.forecast?.burnWarning?.active == true {
                Text(store.forecast?.burnWarning?.message ?? "Burn over safe — cut fan-out")
                    .font(.caption2)
                    .foregroundStyle(.orange)
                    .lineLimit(4)
                Text("Fix: fewer parallel tasks · smaller batches")
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(.orange)
            }
            if let err = store.lastError, !store.isHealthy {
                Text(err)
                    .font(.caption2)
                    .foregroundStyle(.red)
                    .lineLimit(3)
            }
        }
    }

    private var controls: some View {
        VStack(spacing: 6) {
            Button {
                openWindow(id: "ledger")
            } label: {
                Label("Open Ledger", systemImage: "list.bullet.rectangle")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)

            Button {
                openWindow(id: "dashboard")
            } label: {
                Label("Dashboard", systemImage: "gauge.with.dots.needle.67percent")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)

            HStack(spacing: 6) {
                Button("Start") {
                    Task { await store.daemonStart() }
                }
                .disabled(store.isHealthy || store.isBusy)
                Button("Stop") {
                    Task { await store.daemonStop() }
                }
                .disabled(!store.isHealthy || store.isBusy)
                Button("Restart") {
                    Task { await store.daemonRestart() }
                }
                .disabled(store.isBusy)
                Button {
                    Task { await store.refresh() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(store.isBusy)
            }
            .controlSize(.small)
            .buttonStyle(.bordered)

            Button {
                Task { await store.intelTick() }
            } label: {
                Label("Compound tick", systemImage: "arrow.triangle.2.circlepath.circle")
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(store.isBusy)
        }
    }

    private var footer: some View {
        HStack {
            Text(store.status?.version.map { "v\($0)" } ?? "—")
                .font(.caption2)
                .foregroundStyle(.tertiary)
            Spacer()
            if let t = store.lastRefresh {
                Text(t, style: .time)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
            .buttonStyle(.plain)
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }

    private func metricRow(_ title: String, value: String, color: Color = .primary) -> some View {
        HStack {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption.monospacedDigit().weight(.medium))
                .foregroundStyle(color)
        }
    }

    private func formatInt(_ n: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        return f.string(from: NSNumber(value: n)) ?? "\(n)"
    }
}
