import Observation
import SwiftUI
import VelroCore

/// The one screen a signed-out watch shows: what the watch is for, how to
/// sign in, and the language.
struct SignedOutView: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        let strings = model.strings
        NavigationStack {
            ScrollView {
                VStack(spacing: 10) {
                    Image(systemName: "exclamationmark.bubble")
                        .font(.title2)
                        .foregroundStyle(WatchPalette.amber)
                        .accessibilityHidden(true)
                    Text(strings["ops.title"])
                        .font(.headline)
                    if let reason = model.signOutReason {
                        Text(strings.forErrorCode(reason))
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .multilineTextAlignment(.center)
                    }
                    Text(strings["ops.watch.signed_out"])
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                    NavigationLink {
                        WatchSignInView(model: model)
                    } label: {
                        Text(strings["auth.action.sign_in"])
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    LanguageButtons()
                }
                .padding(.horizontal, 4)
            }
        }
    }
}

/// Each language named in itself: how somebody who cannot read the current
/// one finds their own.
struct LanguageButtons: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        HStack(spacing: 4) {
            ForEach(AppLocale.allCases, id: \.self) { locale in
                Button(locale.endonym) { model.choose(locale) }
                    .font(.caption2)
                    .buttonStyle(.bordered)
                    .tint(locale == model.locale ? WatchPalette.amber : nil)
            }
        }
    }
}

/// Staff sign-in, as VELRO Ops does it: the phone, where the code goes, the
/// code. Once; after that the watch renews its own session.
struct WatchSignInView: View {
    @State private var flow: WatchSignInFlow
    private let model: WatchModel

    init(model: WatchModel) {
        self.model = model
        _flow = State(initialValue: WatchSignInFlow(model: model))
    }

    var body: some View {
        let strings = model.strings
        List {
            if let error = flow.error {
                Text(strings.forErrorCode(error.code, context: error.context.arguments))
                    .font(.footnote)
                    .foregroundStyle(.red)
            }
            switch flow.step {
            case .phone: phoneStep(strings)
            case .code: codeStep(strings)
            }
        }
        .navigationTitle(strings["auth.title.sign_in"])
    }

    @ViewBuilder private func phoneStep(_ strings: Strings) -> some View {
        TextField(strings["auth.field.phone"], text: $flow.phone)
            .textContentType(.telephoneNumber)
        Picker(strings["auth.channel.question"], selection: $flow.channel) {
            Text(strings["auth.channel.email"]).tag(API.channelEmail)
            Text(strings["auth.channel.sms"]).tag(API.channelSMS)
        }
        Button {
            Task { await flow.requestCode() }
        } label: {
            working(strings["auth.action.send_code"])
        }
        .disabled(!flow.canSubmitPhone)
    }

    @ViewBuilder private func codeStep(_ strings: Strings) -> some View {
        Text(strings[flow.sentChannel == API.channelEmail ? "auth.hint.code_sent_email" : "auth.hint.code_sent"])
            .font(.footnote)
            .foregroundStyle(.secondary)
        TextField(strings["auth.field.code"], text: $flow.code)
            .textContentType(.oneTimeCode)
        Button {
            Task { await flow.submitCode() }
        } label: {
            working(strings["auth.action.sign_in"])
        }
        .disabled(!flow.canSubmitCode)
        Button {
            Task { await flow.requestCode() }
        } label: {
            Text(flow.resendAfterSeconds > 0
                 ? strings["auth.action.resend_code_in", ["seconds": flow.resendAfterSeconds]]
                 : strings["auth.action.resend_code"])
        }
        .disabled(!flow.canResend)
        Button(strings["common.action.back"]) { flow.back() }
    }

    private func working(_ title: String) -> some View {
        HStack {
            Text(title)
            if flow.isSubmitting {
                Spacer()
                ProgressView().frame(width: 20, height: 20)
            }
        }
    }
}

/// VELRO Ops' SignInModel, for the watch. An SMS costs money, so the resend
/// wait is kept; a development server echoes the code and it is filled in.
@MainActor
@Observable
final class WatchSignInFlow {
    enum Step { case phone, code }

    var step: Step = .phone
    var phone = "" { didSet { error = nil } }
    var code = "" { didSet { if code.count > 8 { code = String(code.prefix(8)) }; error = nil } }
    var channel = API.channelEmail { didSet { error = nil } }
    private(set) var sentChannel = API.channelSMS
    private(set) var isSubmitting = false
    private(set) var error: APIError?
    private(set) var resendAfterSeconds = 0

    private let model: WatchModel
    private var countdown: Task<Void, Never>?

    init(model: WatchModel) {
        self.model = model
        #if DEBUG
        // Nothing can type into the watch simulator from a script, so a
        // development build takes the form from its launch arguments:
        // -VelroDemoPhone +93700000001 -VelroDemoChannel sms
        let defaults = UserDefaults.standard
        if let phone = defaults.string(forKey: "VelroDemoPhone") { self.phone = phone }
        if defaults.string(forKey: "VelroDemoChannel") == "sms" { channel = API.channelSMS }
        #endif
    }

    private var latinPhone: String { Numerals.latin(phone).filter { !$0.isWhitespace } }

    var canSubmitPhone: Bool { latinPhone.filter(\.isNumber).count >= 9 && !isSubmitting }
    var canSubmitCode: Bool { Numerals.latin(code).filter(\.isNumber).count >= 4 && !isSubmitting }
    var canResend: Bool { resendAfterSeconds <= 0 && !isSubmitting }

    func requestCode() async {
        guard canSubmitPhone else { return }
        if step == .code && !canResend { return }
        isSubmitting = true
        error = nil
        model.clearSignOutReason()
        let result = await model.client.send(
            API.requestStaffOtp(phone: latinPhone, locale: model.locale, channel: channel)
        )
        isSubmitting = false
        switch result {
        case .success(let sent):
            step = .code
            sentChannel = sent.channel ?? API.channelSMS
            resendAfterSeconds = sent.resendAfterSeconds
            code = sent.debugCode ?? ""
            startCountdown()
        case .failure(let failure):
            fail(failure)
        }
    }

    func submitCode() async {
        guard canSubmitCode else { return }
        isSubmitting = true
        error = nil
        let result = await model.client.send(
            API.verifyOtp(
                phone: latinPhone, code: Numerals.latin(code).filter(\.isNumber),
                deviceId: model.store.deviceId, locale: model.locale
            )
        )
        isSubmitting = false
        switch result {
        case .success(let session):
            countdown?.cancel()
            if !model.signedIn(session) {
                step = .phone
                code = ""
            }
        case .failure(let failure):
            fail(failure)
        }
    }

    func back() {
        step = .phone
        code = ""
        error = nil
    }

    private func fail(_ failure: APIError) {
        guard failure != .cancelled else { return }
        if failure.code == "OTP_INVALID" { code = "" }
        if failure.code == "OTP_EXPIRED" { step = .phone }
        error = failure
    }

    private func startCountdown() {
        countdown?.cancel()
        countdown = Task { [weak self] in
            while let self, self.resendAfterSeconds > 0 {
                try? await Task.sleep(for: .seconds(1))
                if Task.isCancelled { return }
                self.resendAfterSeconds -= 1
            }
        }
    }
}
