import Foundation
import SwiftUI

@MainActor
final class AegisStore: ObservableObject {
    @Published var isHealthy = false
    @Published var status: RouterStatus?
    @Published var budget: BudgetReport?
    @Published var surplus: SurplusSnapshot?
    @Published var transactions: [LedgerTxn] = []
    @Published var lastError: String?
    @Published var lastRefresh: Date?
    @Published var isBusy = false
    @Published var baseURLString: String = "http://127.0.0.1:8787"
    @Published var daemonMessage: String?
    @Published var intel: IntelStatus?
    @Published var forecast: ForecastInfo?

    private let client = AegisClient()
    private var pollTask: Task<Void, Never>?

    var reserveSignal: String {
        budget?.reserveSignal ?? status?.reserveSignal ?? "—"
    }

    var remainingPct: Double {
        budget?.remainingWeeklyCapacityPercent
            ?? status?.remainingPct
            ?? 0
    }

    var signalColor: Color {
        switch reserveSignal {
        case "ok": return .green
        case "throttle": return .orange
        case "hard_stop": return .red
        default: return isHealthy ? .secondary : .red
        }
    }

    var menuIcon: String {
        if !isHealthy { return "shield.slash" }
        switch reserveSignal {
        case "ok": return "shield.checkered"
        case "throttle": return "exclamationmark.shield"
        case "hard_stop": return "xmark.shield"
        default: return "shield"
        }
    }

    func startPolling(interval: TimeInterval = 8) {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refresh() async {
        if let url = URL(string: baseURLString) {
            await client.setBaseURL(url)
        }
        do {
            let health = try await client.health()
            isHealthy = health.ok
            status = try? await client.status()
            if let br = try? await client.budget() {
                budget = br.budget
                surplus = br.surplus
            }
            if let lr = try? await client.ledger(limit: 150) {
                transactions = lr.transactions ?? []
            } else {
                // fallback local file
                transactions = (try? AegisClient.readLocalLedger(limit: 150)) ?? []
            }
            if let intelStatus = try? await client.intel() {
                intel = intelStatus
                forecast = intelStatus.forecast
            }
            lastError = nil
            lastRefresh = Date()
        } catch {
            isHealthy = false
            status = nil
            // still show local ledger
            if transactions.isEmpty {
                transactions = (try? AegisClient.readLocalLedger(limit: 150)) ?? []
            }
            lastError = error.localizedDescription
            lastRefresh = Date()
        }
    }

    func daemonStart() async {
        await runDaemon(["daemon", "start", "--port", "8787"])
    }

    func daemonStop() async {
        await runDaemon(["daemon", "stop"])
    }

    func daemonRestart() async {
        await runDaemon(["daemon", "restart", "--port", "8787"])
    }

    func intelTick() async {
        isBusy = true
        defer { isBusy = false }
        do {
            let out = try await AegisClient.runAegisCLI(["intel", "tick", "--force-report"])
            daemonMessage = out.trimmingCharacters(in: .whitespacesAndNewlines)
            await refresh()
        } catch {
            daemonMessage = error.localizedDescription
            lastError = error.localizedDescription
        }
    }

    private func runDaemon(_ args: [String]) async {
        isBusy = true
        defer { isBusy = false }
        do {
            let out = try await AegisClient.runAegisCLI(args)
            daemonMessage = out.trimmingCharacters(in: .whitespacesAndNewlines)
            // give process a beat
            try? await Task.sleep(nanoseconds: 600_000_000)
            await refresh()
        } catch {
            daemonMessage = error.localizedDescription
            lastError = error.localizedDescription
        }
    }
}
