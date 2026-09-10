import Foundation

public struct RequestOtpResponse: Decodable, Sendable {
    public let expiresInSeconds: Int
    public let resendAfterSeconds: Int
    /// Only a development server sends this; production never does.
    public let debugCode: String?
    /// What actually carried the code, which is not always what was asked for.
    public let channel: String?
}

public struct ProfileDTO: Decodable, Sendable, Equatable {
    public let id: String
    public let phone: String
    public let fullName: String?
    public let locale: String
    public let roles: [String]
    public let memberSince: String?
    public let completedTrips: Int?
    public let ratingAverage: Double?
    public let ratingCount: Int?
}

/// The HTTP surface, one function per endpoint, named as the Android client's
/// `VelroApi` names them.
public enum API {
    public static let channelSMS = "sms"
    public static let channelTelegram = "telegram"

    public static func requestOtp(phone: String, locale: AppLocale, channel: String) -> Endpoint<RequestOtpResponse> {
        struct Body: Encodable { let phone: String; let locale: String; let channel: String }
        return .post(
            "auth/otp/request",
            body: Body(phone: phone, locale: locale.tag, channel: channel),
            authenticated: false
        )
    }

    public static func verifyOtp(phone: String, code: String, deviceId: String, locale: AppLocale) -> Endpoint<SessionDTO> {
        struct Body: Encodable { let phone: String; let code: String; let deviceId: String; let locale: String }
        return .post(
            "auth/otp/verify",
            body: Body(phone: phone, code: code, deviceId: deviceId, locale: locale.tag),
            authenticated: false
        )
    }

    public static func profile() -> Endpoint<ProfileDTO> { .get("auth/me") }

    public static func updateProfile(fullName: String? = nil, locale: AppLocale? = nil) -> Endpoint<ProfileDTO> {
        struct Body: Encodable { let fullName: String?; let locale: String? }
        return .patch("auth/me", body: Body(fullName: fullName, locale: locale?.tag))
    }

    public static func logoutAllDevices() -> Endpoint<[String: JSONValue]> { .post("auth/logout-all") }
}
