import AppKit
import SwiftUI

@main
struct AegisMenuApp: App {
    @StateObject private var store = AegisStore()

    var body: some Scene {
        MenuBarExtra {
            MenuBarView()
                .environmentObject(store)
                .onAppear {
                    store.startPolling()
                    Task { await store.refresh() }
                }
        } label: {
            Label("Aegis", systemImage: store.menuIcon)
        }
        .menuBarExtraStyle(.window)

        Window("Aegis Ledger", id: "ledger") {
            LedgerView()
                .environmentObject(store)
        }
        .defaultSize(width: 860, height: 520)

        Window("Aegis Dashboard", id: "dashboard") {
            DashboardView()
                .environmentObject(store)
        }
        .defaultSize(width: 560, height: 520)

        Settings {
            SettingsView()
                .environmentObject(store)
        }
    }

    init() {
        // ensure accessory-style presence even if Info.plist is missing in dev runs
        DispatchQueue.main.async {
            NSApp.setActivationPolicy(.accessory)
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var store: AegisStore

    var body: some View {
        Form {
            Section("Router") {
                TextField("Base URL", text: $store.baseURLString)
                HStack {
                    Circle()
                        .fill(store.isHealthy ? Color.green : Color.red)
                        .frame(width: 8, height: 8)
                    Text(store.isHealthy ? "Reachable" : "Unreachable")
                    Spacer()
                    Button("Test") {
                        Task { await store.refresh() }
                    }
                }
            }
            Section("About") {
                Text("Aegis Menu — native macOS control surface for the JIT token supply chain.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Polls /healthz, /v1/aegis/status, /budget, /ledger.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 420, height: 240)
        .onAppear {
            store.startPolling()
        }
    }
}
