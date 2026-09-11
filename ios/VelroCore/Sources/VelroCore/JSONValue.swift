/// A JSON value whose shape is not known in advance.
///
/// Error contexts are free-form: `{"attempts_remaining": 2}` for one code,
/// `{"retry_after_seconds": 40}` for another. They fill placeholders in a
/// translated sentence, so they are kept as data rather than decoded into a
/// type per error.
public enum JSONValue: Sendable, Hashable, Decodable {
    case string(String)
    case int(Int64)
    case double(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int64.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            self = .array(try container.decode([JSONValue].self))
        }
    }

    /// The value as a placeholder argument: numbers stay numbers, so they are
    /// rendered in the reader's digits.
    public var argument: Any? {
        switch self {
        case .string(let value): value
        case .int(let value): value
        case .double(let value): value
        case .bool(let value): value
        case .object, .array: String(describing: self)
        case .null: nil
        }
    }
}

extension Dictionary where Key == String, Value == JSONValue {
    /// A context as placeholder arguments, dropping nulls.
    public var arguments: [String: Any] {
        compactMapValues(\.argument)
    }
}
