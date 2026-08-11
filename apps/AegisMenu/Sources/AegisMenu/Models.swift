import Foundation

// MARK: - API models (router daemon)

struct HealthResponse: Codable, Sendable {
    let ok: Bool
    let service: String?
    let version: String?
}

struct RouterStatus: Codable, Sendable {
    let version: String?
    let reserveSignal: String?
    let remainingPct: Double?
    let reuseHitRatePercent: Double?
    let maxConcurrentDefault: Int?
    let providers: [ProviderInfo]?
    let daemon: DaemonState?
    let endpoints: [String]?

    enum CodingKeys: String, CodingKey {
        case version
        case reserveSignal = "reserve_signal"
        case remainingPct = "remaining_pct"
        case reuseHitRatePercent = "reuse_hit_rate_percent"
        case maxConcurrentDefault = "max_concurrent_default"
        case providers, daemon, endpoints
    }
}

struct ProviderInfo: Codable, Identifiable, Sendable {
    var id: String { name }
    let name: String
    let kind: String?
    let defaultModel: String?
    let credentials: Bool?

    enum CodingKeys: String, CodingKey {
        case name, kind, credentials
        case defaultModel = "default_model"
    }
}

struct DaemonState: Codable, Sendable {
    let host: String?
    let port: Int?
    let requests: Int?
    let pipelineRuns: Int?
    let pid: Int?
    let managedBy: String?

    enum CodingKeys: String, CodingKey {
        case host, port, requests, pid
        case pipelineRuns = "pipeline_runs"
        case managedBy = "managed_by"
    }
}

struct BudgetResponse: Codable, Sendable {
    let ok: Bool
    let budget: BudgetReport?
    let surplus: SurplusSnapshot?
    let version: String?
}

struct BudgetReport: Codable, Sendable {
    let week: String?
    let totalTransactions: Int?
    let totalTokensConsumed: Int?
    let totalTokensSaved: Int?
    let overallTokenReductionPercent: Double?
    let weeklyTokenCap: Int?
    let remainingWeeklyCapacityPercent: Double?
    let reserveSignal: String?
    let reserveFloor: Double?
    let reuseHitRatePercent: Double?
    let netFinancialSavingsDollars: Double?
    let lifetimeTransactions: Int?

    enum CodingKeys: String, CodingKey {
        case week
        case totalTransactions = "total_transactions"
        case totalTokensConsumed = "total_tokens_consumed"
        case totalTokensSaved = "total_tokens_saved"
        case overallTokenReductionPercent = "overall_token_reduction_percent"
        case weeklyTokenCap = "weekly_token_cap"
        case remainingWeeklyCapacityPercent = "remaining_weekly_capacity_percent"
        case reserveSignal = "reserve_signal"
        case reserveFloor = "reserve_floor"
        case reuseHitRatePercent = "reuse_hit_rate_percent"
        case netFinancialSavingsDollars = "net_financial_savings_dollars"
        case lifetimeTransactions = "lifetime_transactions"
    }
}

struct SurplusSnapshot: Codable, Sendable {
    let availableCredits: Int?
    let headroom: Int?
    let lifetimeSaved: Int?
    let canInvest: Bool?
    let week: String?

    enum CodingKeys: String, CodingKey {
        case availableCredits = "available_credits"
        case headroom
        case lifetimeSaved = "lifetime_saved"
        case canInvest = "can_invest"
        case week
    }
}

struct LedgerResponse: Codable, Sendable {
    let ok: Bool
    let count: Int?
    let limit: Int?
    let week: String?
    let summary: BudgetReport?
    let transactions: [LedgerTxn]?
    let version: String?
}

// MARK: - Intelligence Layer

struct IntelStatus: Codable, Sendable {
    let ok: Bool?
    let config: IntelConfig?
    let state: IntelState?
    let forecast: ForecastInfo?
    let cacheHitRatePercent: Double?
    let signals: [IntelSignal]?
    let bgTickRunning: Bool?
    let budgetAware: BudgetAwareInfo?

    enum CodingKeys: String, CodingKey {
        case ok, config, state, forecast, signals
        case cacheHitRatePercent = "cache_hit_rate_percent"
        case bgTickRunning = "bg_tick_running"
        case budgetAware = "budget_aware"
    }
}

struct IntelConfig: Codable, Sendable {
    let autoTick: Bool?
    let autoInvest: Bool?
    let autoApplyFixes: Bool?
    let autoMemory: Bool?

    enum CodingKeys: String, CodingKey {
        case autoTick = "auto_tick"
        case autoInvest = "auto_invest"
        case autoApplyFixes = "auto_apply_fixes"
        case autoMemory = "auto_memory"
    }
}

struct IntelState: Codable, Sendable {
    let ticks: Int?
    let autoInvests: Int?
    let fixesApplied: Int?
    let lastTickTs: String?
    let compoundCycles: Int?

    enum CodingKeys: String, CodingKey {
        case ticks
        case autoInvests = "auto_invests"
        case fixesApplied = "fixes_applied"
        case lastTickTs = "last_tick_ts"
        case compoundCycles = "compound_cycles"
    }
}

struct ForecastInfo: Codable, Sendable {
    let projectedSignal: String?
    let projectedRemainingPct: Double?
    let recommendedDailyBudget: Double?
    let avgDailyBurn: Double?
    let etaDaysToReserve: Double?
    let advice: [String]?
    let burnWarning: BurnWarning?
    let burnWarningMultiplier: Double?
    let burnStatus: BurnStatusInfo?

    enum CodingKeys: String, CodingKey {
        case advice
        case projectedSignal = "projected_signal"
        case projectedRemainingPct = "projected_remaining_pct"
        case recommendedDailyBudget = "recommended_daily_budget"
        case avgDailyBurn = "avg_daily_burn"
        case etaDaysToReserve = "eta_days_to_reserve"
        case burnWarning = "burn_warning"
        case burnWarningMultiplier = "burn_warning_multiplier"
        case burnStatus = "burn_status"
    }
}

struct BurnStatusInfo: Codable, Sendable {
    let level: String?
    let ratio: Double?
    let ratioPct: Double?
    let message: String?
    let fix: String?
    let fixDetail: String?

    enum CodingKeys: String, CodingKey {
        case level, ratio, message, fix
        case ratioPct = "ratio_pct"
        case fixDetail = "fix_detail"
    }
}

struct BudgetAwareInfo: Codable, Sendable {
    let band: String?
    let level: String?
    let menuSummary: String?
    let modulesShed: [String]?
    let modulesThrottled: [String]?
    let recommendedWorkers: Int?
    let enabled: Bool?

    enum CodingKeys: String, CodingKey {
        case band, level, enabled
        case menuSummary = "menu_summary"
        case modulesShed = "modules_shed"
        case modulesThrottled = "modules_throttled"
        case recommendedWorkers = "recommended_workers"
    }
}

struct BurnWarning: Codable, Sendable {
    let active: Bool?
    let avgDailyBurn: Double?
    let safeDaily: Double?
    let overPct: Double?
    let multiplier: Double?
    let message: String?
    let fix: String?
    let fixDetail: String?

    enum CodingKeys: String, CodingKey {
        case active, message, fix, multiplier
        case avgDailyBurn = "avg_daily_burn"
        case safeDaily = "safe_daily"
        case overPct = "over_pct"
        case fixDetail = "fix_detail"
    }
}

struct IntelSignal: Codable, Identifiable, Sendable {
    var id: String { signalId ?? title ?? UUID().uuidString }
    let signalId: String?
    let severity: String?
    let title: String?
    let detail: String?

    enum CodingKeys: String, CodingKey {
        case severity, title, detail
        case signalId = "id"
    }
}

struct LedgerTxn: Codable, Identifiable, Sendable, Hashable {
    let id: String
    let ts: String?
    let week: String?
    let kind: String?
    let task: String?
    let mode: String?
    let rawIn: Int?
    let processedIn: Int?
    let rawOut: Int?
    let processedOut: Int?
    let tokensSaved: Int?
    let packId: String?
    let reuse: Bool?
    let project: String?
    let savingsDollars: Double?

    enum CodingKeys: String, CodingKey {
        case id, ts, week, kind, task, mode, reuse, project
        case rawIn = "raw_in"
        case processedIn = "processed_in"
        case rawOut = "raw_out"
        case processedOut = "processed_out"
        case tokensSaved = "tokens_saved"
        case packId = "pack_id"
        case savingsDollars = "savings_dollars"
    }
}
