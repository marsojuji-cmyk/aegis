import SwiftUI

struct LedgerView: View {
    @EnvironmentObject private var store: AegisStore
    @State private var query = ""
    @State private var kindFilter: String = "all"

    private var kinds: [String] {
        let set = Set(store.transactions.compactMap(\.kind))
        return ["all"] + set.sorted()
    }

    private var filtered: [LedgerTxn] {
        store.transactions.filter { txn in
            let kindOK = kindFilter == "all" || txn.kind == kindFilter
            guard kindOK else { return false }
            if query.isEmpty { return true }
            let q = query.lowercased()
            return (txn.task?.lowercased().contains(q) ?? false)
                || (txn.kind?.lowercased().contains(q) ?? false)
                || (txn.id.lowercased().contains(q))
                || (txn.mode?.lowercased().contains(q) ?? false)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            if filtered.isEmpty {
                ContentUnavailableView(
                    "No transactions",
                    systemImage: "scroll",
                    description: Text(
                        store.isHealthy
                            ? "Ledger is empty for this filter."
                            : "Daemon offline — showing local ~/.aegis/ledger.jsonl when available."
                    )
                )
            } else {
                Table(filtered) {
                    TableColumn("Time") { txn in
                        Text(shortTS(txn.ts))
                            .font(.caption.monospacedDigit())
                    }
                    .width(min: 120, ideal: 140)

                    TableColumn("Kind") { txn in
                        Text(txn.kind ?? "—")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(kindColor(txn.kind))
                    }
                    .width(min: 80, ideal: 100)

                    TableColumn("Task") { txn in
                        Text(txn.task ?? "—")
                            .lineLimit(1)
                            .font(.caption)
                    }
                    .width(min: 160, ideal: 240)

                    TableColumn("Saved") { txn in
                        Text(formatInt(txn.tokensSaved ?? 0))
                            .font(.caption.monospacedDigit())
                            .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .width(min: 70, ideal: 80)

                    TableColumn("In") { txn in
                        Text("\(txn.processedIn ?? 0)/\(txn.rawIn ?? 0)")
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    .width(min: 80, ideal: 90)

                    TableColumn("$") { txn in
                        Text(String(format: "%.4f", txn.savingsDollars ?? 0))
                            .font(.caption2.monospacedDigit())
                    }
                    .width(min: 60, ideal: 70)

                    TableColumn("Reuse") { txn in
                        Image(systemName: (txn.reuse == true) ? "arrow.triangle.2.circlepath" : "minus")
                            .foregroundStyle((txn.reuse == true) ? Color.green : Color.secondary)
                    }
                    .width(50)
                }
            }
            Divider()
            summaryBar
        }
        .navigationTitle("Aegis Ledger")
        .frame(minWidth: 720, minHeight: 420)
        .task { await store.refresh() }
    }

    private var toolbar: some View {
        HStack(spacing: 12) {
            TextField("Filter task / kind…", text: $query)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 280)

            Picker("Kind", selection: $kindFilter) {
                ForEach(kinds, id: \.self) { k in
                    Text(k).tag(k)
                }
            }
            .frame(width: 160)

            Spacer()

            Text("\(filtered.count) rows")
                .font(.caption)
                .foregroundStyle(.secondary)

            Button {
                Task { await store.refresh() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(store.isBusy)
        }
        .padding(10)
    }

    private var summaryBar: some View {
        HStack(spacing: 16) {
            Label(store.isHealthy ? "Live" : "Local", systemImage: store.isHealthy ? "circle.fill" : "circle")
                .font(.caption2)
                .foregroundStyle(store.isHealthy ? .green : .orange)
            if let week = store.budget?.week {
                Text(week).font(.caption2.monospaced()).foregroundStyle(.secondary)
            }
            if let saved = store.budget?.totalTokensSaved {
                Text("saved \(formatInt(saved))")
                    .font(.caption2.monospacedDigit())
            }
            if let signal = store.budget?.reserveSignal {
                Text(signal)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(store.signalColor)
            }
            Spacer()
            if let dollars = store.budget?.netFinancialSavingsDollars {
                Text(String(format: "$%.4f week", dollars))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private func shortTS(_ ts: String?) -> String {
        guard let ts else { return "—" }
        // 2026-08-08T18:49:25+00:00 → 08-08 18:49
        if ts.count >= 16 {
            let d = ts.dropFirst(5).prefix(11).replacingOccurrences(of: "T", with: " ")
            return String(d)
        }
        return ts
    }

    private func formatInt(_ n: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        return f.string(from: NSNumber(value: n)) ?? "\(n)"
    }

    private func kindColor(_ kind: String?) -> Color {
        switch kind {
        case "pack": return .blue
        case "reuse_hit": return .green
        case "router_run": return .purple
        case "land", "output": return .teal
        case "legacy_import": return .secondary
        default: return .primary
        }
    }
}
