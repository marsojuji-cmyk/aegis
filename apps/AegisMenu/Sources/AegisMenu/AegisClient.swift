import Foundation

/// HTTP client for the Aegis router daemon (+ local ledger fallback).
actor AegisClient {
    var baseURL: URL
    private let session: URLSession

    init(baseURL: URL = URL(string: "http://127.0.0.1:8787")!) {
        self.baseURL = baseURL
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 4
        cfg.timeoutIntervalForResource = 8
        self.session = URLSession(configuration: cfg)
    }

    func setBaseURL(_ url: URL) {
        baseURL = url
    }

    // MARK: - HTTP

    func health() async throws -> HealthResponse {
        try await get("/healthz")
    }

    func status() async throws -> RouterStatus {
        try await get("/v1/aegis/status")
    }

    func budget() async throws -> BudgetResponse {
        try await get("/v1/aegis/budget")
    }

    func ledger(limit: Int = 100, week: String? = nil) async throws -> LedgerResponse {
        var path = "/v1/aegis/ledger?limit=\(limit)"
        if let week, !week.isEmpty {
            path += "&week=\(week.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? week)"
        }
        return try await get(path)
    }

    func intel() async throws -> IntelStatus {
        try await get("/v1/aegis/intel")
    }

    func intelTick(forceReport: Bool = false) async throws -> [String: AnyCodableJSON] {
        // lightweight: fire tick via process CLI when needed
        _ = forceReport
        throw AegisClientError.cli("use CLI tick")
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            throw AegisClientError.badURL(path)
        }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else {
            throw AegisClientError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw AegisClientError.http(http.statusCode)
        }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw AegisClientError.decode(error.localizedDescription)
        }
    }

    // MARK: - Local fallback (daemon down)

    nonisolated static var aegisHome: URL {
        if let raw = ProcessInfo.processInfo.environment["AEGIS_HOME"], !raw.isEmpty {
            return URL(fileURLWithPath: raw, isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".aegis", isDirectory: true)
    }

    nonisolated static func readLocalLedger(limit: Int = 100) throws -> [LedgerTxn] {
        let path = aegisHome.appendingPathComponent("ledger.jsonl")
        guard FileManager.default.fileExists(atPath: path.path) else { return [] }
        let text = try String(contentsOf: path, encoding: .utf8)
        let decoder = JSONDecoder()
        var rows: [LedgerTxn] = []
        for line in text.split(separator: "\n", omittingEmptySubsequences: true).reversed() {
            guard let data = line.data(using: .utf8) else { continue }
            if let txn = try? decoder.decode(LedgerTxn.self, from: data) {
                rows.append(txn)
                if rows.count >= limit { break }
            }
        }
        return rows
    }

    // MARK: - Process control (daemon CLI)

    nonisolated static func runAegisCLI(_ args: [String]) async throws -> String {
        try await withCheckedThrowingContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                do {
                    let out = try Self.syncRunAegisCLI(args)
                    cont.resume(returning: out)
                } catch {
                    cont.resume(throwing: error)
                }
            }
        }
    }

    nonisolated private static func syncRunAegisCLI(_ args: [String]) throws -> String {
        let python = resolvePython()
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: python)
        proc.arguments = ["-m", "aegis"] + args
        var env = ProcessInfo.processInfo.environment
        // Prefer product tree for editable install
        let src = defaultSrcRoot()
        if FileManager.default.fileExists(atPath: src) {
            let prev = env["PYTHONPATH"] ?? ""
            env["PYTHONPATH"] = prev.isEmpty ? src : "\(src):\(prev)"
        }
        proc.environment = env
        let pipe = Pipe()
        let err = Pipe()
        proc.standardOutput = pipe
        proc.standardError = err
        try proc.run()
        proc.waitUntilExit()
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        let errData = err.fileHandleForReading.readDataToEndOfFile()
        let out = String(data: data, encoding: .utf8) ?? ""
        let errOut = String(data: errData, encoding: .utf8) ?? ""
        if proc.terminationStatus != 0 {
            throw AegisClientError.cli(errOut.isEmpty ? out : errOut)
        }
        return out.isEmpty ? errOut : out
    }

    nonisolated private static func resolvePython() -> String {
        let candidates = [
            "/usr/bin/python3",
            ProcessInfo.processInfo.environment["AEGIS_PYTHON"] ?? "",
        ]
        for c in candidates where !c.isEmpty {
            if FileManager.default.isExecutableFile(atPath: c) { return c }
        }
        return "/usr/bin/python3"
    }

    nonisolated private static func defaultSrcRoot() -> String {
        // apps/AegisMenu → ../../src when installed beside product
        let home = FileManager.default.homeDirectoryForCurrentUser
        return home.appendingPathComponent("Projects/aegis/src").path
    }
}

/// Minimal JSON value for optional dynamic payloads (unused reserved).
struct AnyCodableJSON: Codable, Sendable {}

enum AegisClientError: LocalizedError {
    case badURL(String)
    case invalidResponse
    case http(Int)
    case decode(String)
    case cli(String)

    var errorDescription: String? {
        switch self {
        case .badURL(let p): return "Bad URL: \(p)"
        case .invalidResponse: return "Invalid HTTP response"
        case .http(let c): return "HTTP \(c)"
        case .decode(let m): return "Decode: \(m)"
        case .cli(let m): return "CLI: \(m)"
        }
    }
}
