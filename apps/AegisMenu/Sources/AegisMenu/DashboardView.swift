import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var store: AegisStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                headerCards
                capacitySection
                intelligenceSection
                providersSection
                endpointsSection
            }
            .padding(20)
        }
        .frame(minWidth: 520, minHeight: 400)
        .navigationTitle("Aegis Dashboard")
        .toolbar {
            ToolbarItem {
                Button {
                    Task { await store.refresh() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
        }
        .task { await store.refresh() }
    }

    private var headerCards: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            card(
                title: "Router",
                value: store.isHealthy ? "Online" : "Offline",
                subtitle: store.status?.version.map { "v\($0)" } ?? store.baseURLString,
                color: store.isHealthy ? .green : .red
            )
            card(
                title: "Reserve",
                value: store.reserveSignal.uppercased(),
                subtitle: String(format: "%.1f%% capacity left", store.remainingPct),
                color: store.signalColor
            )
            card(
                title: "Saved (week)",
                value: formatInt(store.budget?.totalTokensSaved ?? 0),
                subtitle: "tokens",
                color: .blue
            )
            card(
                title: "Reuse",
                value: String(format: "%.1f%%", store.budget?.reuseHitRatePercent ?? store.status?.reuseHitRatePercent ?? 0),
                subtitle: "hit rate",
                color: .purple
            )
            card(
                title: "Surplus credits",
                value: formatInt(store.surplus?.availableCredits ?? 0),
                subtitle: store.surplus?.canInvest == true ? "investable" : "frozen / empty",
                color: .orange
            )
            card(
                title: "Week $ saved",
                value: String(format: "$%.4f", store.budget?.netFinancialSavingsDollars ?? 0),
                subtitle: store.budget?.week ?? "—",
                color: .teal
            )
        }
    }

    private var capacitySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Weekly capacity")
                .font(.headline)
            let used = 1.0 - (store.remainingPct / 100.0)
            ProgressView(value: min(max(used, 0), 1)) {
                Text("Consumed")
            } currentValueLabel: {
                Text(String(format: "%.1f%% used · cap %@",
                            used * 100,
                            formatInt(store.budget?.weeklyTokenCap ?? 1_000_000)))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .tint(store.signalColor)

            if let floor = store.budget?.reserveFloor {
                Text(String(format: "Reserve floor ≥ %.0f%%", floor * 100))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
    }

    private var intelligenceSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Intelligence Layer")
                .font(.headline)
            HStack {
                Label(
                    (store.intel?.config?.autoTick == true) ? "Auto-tick ON" : "Auto-tick off",
                    systemImage: "brain"
                )
                .font(.caption)
                Spacer()
                if let c = store.intel?.state?.compoundCycles {
                    Text("cycles \(c)")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
            if let ba = store.intel?.budgetAware {
                VStack(alignment: .leading, spacing: 4) {
                    Label(ba.menuSummary ?? "Budget: ok", systemImage: "gauge.with.dots.needle.67percent")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(
                            ba.band == "emergency" ? Color.red
                                : (ba.band == "adaptive" ? Color.orange : Color.secondary)
                        )
                    if let shed = ba.modulesShed, !shed.isEmpty {
                        Text("Shed: \(shed.joined(separator: ", "))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let thr = ba.modulesThrottled, !thr.isEmpty {
                        Text("Throttled: \(thr.prefix(6).joined(separator: ", "))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    if let w = ba.recommendedWorkers {
                        Text("Workers cap: \(w)")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.blue.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
            }
            if let fc = store.forecast {
                Text("Forecast: \(fc.projectedSignal?.uppercased() ?? "—") · safe \(Int(fc.recommendedDailyBudget ?? 0))/day")
                    .font(.caption)
                if let burn = fc.avgDailyBurn {
                    Text(String(format: "Avg burn %.0f tok/day", burn))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                if let bs = fc.burnStatus, let level = bs.level, level != "ok" {
                    let color: Color = level == "critical" ? .red : (level == "warn" ? .orange : .yellow)
                    VStack(alignment: .leading, spacing: 4) {
                        Label("Burn \(level)", systemImage: "flame.fill")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(color)
                        Text(bs.message ?? "")
                            .font(.caption2)
                            .foregroundStyle(color)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(bs.fixDetail ?? "Cut fan-out: fewer parallel tasks and smaller batches.")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(color)
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                } else if let bw = fc.burnWarning, bw.active == true {
                    VStack(alignment: .leading, spacing: 4) {
                        Label("Burn warning", systemImage: "flame.fill")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.orange)
                        Text(bw.message ?? "Daily spend is over safe allowance.")
                            .font(.caption2)
                            .foregroundStyle(.orange)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(bw.fixDetail ?? "Cut fan-out: fewer parallel tasks and smaller batches.")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(.orange)
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                }
                if let advice = fc.advice?.prefix(4) {
                    ForEach(Array(advice), id: \.self) { line in
                        Text("• \(line)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            if let sigs = store.intel?.signals, !sigs.isEmpty {
                Text("Course corrections")
                    .font(.caption.weight(.semibold))
                ForEach(sigs.prefix(4)) { s in
                    Text("[\(s.severity ?? "?")] \(s.title ?? "")")
                        .font(.caption2)
                        .foregroundStyle(s.severity == "critical" || s.severity == "high" ? Color.orange : Color.secondary)
                }
            }
            Button("Run compound tick") {
                Task { await store.intelTick() }
            }
            .controlSize(.small)
        }
        .padding()
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
    }

    private var providersSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Providers")
                .font(.headline)
            if let providers = store.status?.providers, !providers.isEmpty {
                ForEach(providers) { p in
                    HStack {
                        Image(systemName: (p.credentials == true) ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle((p.credentials == true) ? .green : .secondary)
                        Text(p.name)
                            .fontWeight(.medium)
                        Text(p.defaultModel ?? "")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(p.kind ?? "")
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(.quaternary, in: Capsule())
                    }
                }
            } else {
                Text(store.isHealthy ? "No providers listed" : "Connect daemon to list providers")
                    .foregroundStyle(.secondary)
                    .font(.caption)
            }
        }
        .padding()
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
    }

    private var endpointsSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Endpoints")
                .font(.headline)
            if let eps = store.status?.endpoints {
                ForEach(eps, id: \.self) { ep in
                    Text(ep)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
            } else {
                Text("GET /healthz · /v1/aegis/status · /v1/aegis/budget · /v1/aegis/ledger")
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
    }

    private func card(title: String, value: String, subtitle: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.weight(.semibold).monospacedDigit())
                .foregroundStyle(color)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Text(subtitle)
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
    }

    private func formatInt(_ n: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        return f.string(from: NSNumber(value: n)) ?? "\(n)"
    }
}
