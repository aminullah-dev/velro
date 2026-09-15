import SwiftUI
import VelroCore

/// Staff sign-in: phone, where the code should go, the code, in.
struct SignInView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model: SignInModel

    init(ops: OpsModel) {
        _model = State(initialValue: SignInModel(ops: ops))
    }

    var body: some View {
        ScrollView {
            VStack(spacing: Spacing.s5) {
                brand
                languages
                form
            }
            .frame(maxWidth: 420)
            .padding(Spacing.s6)
            .frame(maxWidth: .infinity)
        }
        .background(Palette.background)
    }

    private var brand: some View {
        VStack(spacing: Spacing.s1) {
            Text(strings["app.name"])
                .opsFont(.headline, weight: .bold)
                .foregroundStyle(Palette.accent)
            Text(strings["ops.title"])
                .opsFont(.label)
                .foregroundStyle(Palette.textMuted)
        }
        .padding(.top, Spacing.s8)
    }

    /// Each language named in itself: the picker is how somebody who cannot
    /// read the current language finds their own.
    private var languages: some View {
        @Bindable var ops = ops
        return Picker(selection: $ops.locale) {
            ForEach(AppLocale.allCases, id: \.self) { locale in
                Text(locale.endonym).tag(locale)
            }
        } label: {
            EmptyView()
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .frame(maxWidth: 280)
        .accessibilityIdentifier("signin.language")
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: Spacing.s4) {
            Text(strings["admin.signin.title"])
                .opsFont(.title, weight: .bold)
                .foregroundStyle(Palette.text)

            if let reason = ops.signOutReason {
                Banner(strings.forErrorCode(reason), tone: .error)
            }
            if let error = model.error {
                Banner(strings.forErrorCode(error.code, context: error.context.arguments), tone: .error)
            }

            switch model.step {
            case .phone: phoneStep
            case .code: codeStep
            }
        }
        .opsCard(padding: Spacing.s5)
    }

    @ViewBuilder private var phoneStep: some View {
        @Bindable var model = model
        field(strings["auth.field.phone"]) {
            TextField("0700 000 001", text: $model.phone)
                .textContentType(.telephoneNumber)
                #if os(iOS)
                .keyboardType(.phonePad)
                #endif
                .onSubmit { Task { await model.requestCode() } }
                .accessibilityIdentifier("signin.phone")
        }
        VStack(alignment: .leading, spacing: Spacing.s1) {
            Text(strings["auth.channel.question"])
                .opsFont(.label)
                .foregroundStyle(Palette.textMuted)
            Picker(selection: $model.channel) {
                Text(strings["auth.channel.email"]).tag(API.channelEmail)
                Text(strings["auth.channel.sms"]).tag(API.channelSMS)
            } label: {
                EmptyView()
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .accessibilityIdentifier("signin.channel")
        }
        primaryButton(strings["auth.action.send_code"], enabled: model.canSubmitPhone, identifier: "signin.send") {
            await model.requestCode()
        }
    }

    @ViewBuilder private var codeStep: some View {
        @Bindable var model = model
        // Where the code actually went, which is not always where it was
        // asked to go.
        Text(strings[hintKey])
            .opsFont(.label, weight: .regular)
            .foregroundStyle(Palette.textMuted)
        field(strings["auth.field.code"]) {
            TextField("", text: $model.code)
                .textContentType(.oneTimeCode)
                #if os(iOS)
                .keyboardType(.numberPad)
                #endif
                .onSubmit { Task { await model.submitCode() } }
                .accessibilityIdentifier("signin.code")
        }
        primaryButton(strings["auth.action.sign_in"], enabled: model.canSubmitCode, identifier: "signin.verify") {
            await model.submitCode()
        }
        HStack {
            Button(strings["common.action.back"]) { model.back() }
            Spacer()
            Button(resendTitle) { Task { await model.requestCode() } }
                .disabled(!model.canResend)
        }
        .buttonStyle(.borderless)
        .opsFont(.label)
    }

    private var hintKey: String {
        switch model.sentChannel {
        case API.channelEmail: "auth.hint.code_sent_email"
        case API.channelTelegram: "auth.hint.code_sent_telegram"
        default: "auth.hint.code_sent"
        }
    }

    private var resendTitle: String {
        model.resendAfterSeconds > 0
            ? strings["auth.action.resend_code_in", ["seconds": model.resendAfterSeconds]]
            : strings["auth.action.resend_code"]
    }

    /// A labelled field. Numbers are always laid out left to right, even in
    /// a right-to-left form.
    private func field(_ label: String, @ViewBuilder input: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            Text(label)
                .opsFont(.label)
                .foregroundStyle(Palette.textMuted)
            input()
                .textFieldStyle(.roundedBorder)
                .font(.system(.title3, design: .monospaced))
                .environment(\.layoutDirection, .leftToRight)
                .autocorrectionDisabled()
        }
    }

    private func primaryButton(
        _ title: String, enabled: Bool, identifier: String, action: @escaping @MainActor () async -> Void
    ) -> some View {
        Button {
            Task { await action() }
        } label: {
            Group {
                if model.isSubmitting {
                    ProgressView().controlSize(.small)
                } else {
                    Text(title).opsFont(.body, weight: .medium)
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, Spacing.s1)
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .disabled(!enabled)
        .accessibilityIdentifier(identifier)
    }
}
