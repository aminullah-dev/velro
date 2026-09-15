import Observation
import SwiftUI
import VelroCore

/// The audit log, section 59 (the panel's Audit.tsx): append-only, newest
/// first, scrolling on into older pages, narrowed by action or by what kind of
/// thing it happened to. Only the changed fields are stored, which is what
/// keeps a row readable a year later; each shows them as before → after.
///
/// Other screens open it with `navigator.open(.audit, filter:)`:
/// "action:<action>" or "entity:<type>".
struct AuditView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpAuditModel()
    @State private var selectedID: String?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 460) {
                    list(isSplit: true)
                } detail: {
                    if let entry = model.pager.items.first(where: { $0.id == selectedID }) {
                        OpAuditDetailView(entry: entry, model: model).id(entry.id)
                    } else {
                        OpNothingSelected(messageKey: "ops.audit.choose", systemImage: "list.bullet.rectangle")
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AuditEntry.self) { entry in
                        OpAuditDetailView(entry: entry, model: model)
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.audit"])
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Menu {
                    Picker(strings["admin.col.action"], selection: filterBinding(\.action)) {
                        Text(strings["admin.filter.all"]).tag(String?.none)
                        ForEach(model.knownActions, id: \.self) { Text(verbatim: $0).tag(String?.some($0)) }
                    }
                    .pickerStyle(.menu)
                    Picker(strings["admin.col.entity"], selection: filterBinding(\.entityType)) {
                        Text(strings["admin.filter.all"]).tag(String?.none)
                        ForEach(model.knownEntities, id: \.self) { Text(verbatim: $0).tag(String?.some($0)) }
                    }
                    .pickerStyle(.menu)
                } label: {
                    Label(strings["admin.col.action"], systemImage: model.isFiltered
                          ? "line.3.horizontal.decrease.circle.fill" : "line.3.horizontal.decrease.circle")
                }
                OpRefreshButton { [model] in await model.pager.refresh() }
            }
        }
        .task { [model, ops] in
            model.apply(deepLink: ops.navigator.takeFilter(for: .audit))
            await model.reload(ops)
        }
        .poll(every: .seconds(60)) { [model] in await model.pager.refresh() }
    }

    private func filterBinding(_ key: ReferenceWritableKeyPath<OpAuditModel, String?>) -> Binding<String?> {
        Binding(get: { model[keyPath: key] }, set: { value in
            guard value != model[keyPath: key] else { return }
            model[keyPath: key] = value
            selectedID = nil
            Task { [model, ops] in await model.reload(ops) }
        })
    }

    @ViewBuilder
    private func list(isSplit: Bool) -> some View {
        VStack(spacing: 0) {
            if model.isFiltered {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: Spacing.s2) {
                        if let action = model.action {
                            filterPill("admin.col.action", value: action) { filterBinding(\.action).wrappedValue = nil }
                        }
                        if let entity = model.entityType {
                            filterPill("admin.col.entity", value: entity) { filterBinding(\.entityType).wrappedValue = nil }
                        }
                    }
                    .padding(.horizontal, Spacing.s4)
                    .padding(.vertical, Spacing.s2)
                }
                Divider()
            }
            let pager = model.pager
            if pager.isFirstLoad {
                LoadingView()
            } else if let error = pager.error {
                ErrorView(error: error) { [model, ops] in await model.reload(ops) }
            } else if pager.items.isEmpty {
                EmptyStateView(messageKey: "admin.empty.audit", systemImage: "list.bullet.rectangle")
            } else {
                List(selection: isSplit ? $selectedID : .constant(nil)) {
                    ForEach(pager.items) { entry in
                        if isSplit {
                            OpAuditRowView(entry: entry).tag(entry.id)
                        } else {
                            NavigationLink(value: entry) { OpAuditRowView(entry: entry) }
                        }
                    }
                    OpPagerFooter(pager: pager)
                }
                .listStyle(.plain)
                // Selected beside its detail: a light ground the row's own ink reads on.
                .tint(isSplit ? Palette.bannerInfo : Palette.accent)
                .scrollContentBackground(.hidden)
                .refreshable { await pager.refresh() }
            }
        }
    }

    private func filterPill(_ labelKey: String, value: String, clear: @escaping () -> Void) -> some View {
        HStack(spacing: Spacing.s1) {
            Text(strings[labelKey]).foregroundStyle(Palette.textMuted)
            LTRText(value).foregroundStyle(Palette.text)
            Button(action: clear) {
                Image(systemName: "xmark.circle.fill").accessibilityLabel(strings["admin.filter.all"])
            }
            .buttonStyle(.borderless)
        }
        .opsFont(.caption)
        .padding(.horizontal, Spacing.s3)
        .padding(.vertical, 4)
        .background(Palette.surfaceMuted, in: Capsule())
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpAuditModel {
    var action: String?
    var entityType: String?
    let pager = OpPager<AuditEntry>(pageSize: 50)
    /// Every action and entity type seen so far, for the filter menus: the
    /// server has no list of them, and a free-text box invites typos that
    /// match nothing.
    private(set) var seenActions: Set<String> = []
    private(set) var seenEntities: Set<String> = []

    var isFiltered: Bool { action != nil || entityType != nil }

    var knownActions: [String] {
        (seenActions.union(Self.commonActions).union(action.map { [$0] } ?? [])).sorted()
    }

    var knownEntities: [String] {
        (seenEntities.union(Self.commonEntities).union(entityType.map { [$0] } ?? [])).sorted()
    }

    private static let commonActions: Set<String> = [
        "driver.approved", "driver.suspended", "user.suspended", "user.reinstated", "auth.signed_in",
    ]
    private static let commonEntities: Set<String> = ["driver", "user", "trip", "booking", "vehicle"]

    func apply(deepLink: String?) {
        guard let deepLink else { return }
        let parts = deepLink.split(separator: ":", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return }
        switch parts[0] {
        case "action": action = parts[1]
        case "entity": entityType = parts[1]
        default: break
        }
    }

    func reload(_ ops: OpsModel) async {
        let action = action
        let entityType = entityType
        await pager.reload { [weak self, ops] limit, offset in
            let result = await ops.sendWithMeta(AdminAPI.audit(action: action, entityType: entityType, limit: limit, offset: offset))
            if case .success(let page) = result { self?.note(page.items) }
            return result
        }
    }

    private func note(_ entries: [AuditEntry]) {
        seenActions.formUnion(entries.map(\.action))
        seenEntities.formUnion(entries.map(\.entityType))
    }
}

// MARK: - Reading a change

enum OpAuditDiff {
    struct Change: Identifiable {
        let field: String
        let before: String?
        let after: String?
        var id: String { field }
    }

    /// Every field either side mentions, in a stable order; a field with no
    /// value on either side says nothing and is left out (Audit.tsx).
    static func changes(_ entry: AuditEntry) -> [Change] {
        let before = entry.before ?? [:]
        let after = entry.after ?? [:]
        let fields = Set(before.keys).union(after.keys).sorted()
        return fields.compactMap { field in
            let from = before[field].flatMap(text)
            let to = after[field].flatMap(text)
            if from == nil && to == nil { return nil }
            return Change(field: field, before: from, after: to)
        }
    }

    /// "approval_status: PENDING → APPROVED  ·  reason: documents".
    static func summary(_ entry: AuditEntry) -> String {
        let parts = changes(entry).map { change -> String in
            switch (change.before, change.after) {
            case let (from?, to?): "\(change.field): \(from) → \(to)"
            case let (nil, to?): "\(change.field): \(to)"
            case let (from?, nil): "\(change.field): \(from) → ∅"
            case (nil, nil): change.field
            }
        }
        // The server's own words, Latin and left to right: the dot sits
        // beside letters, never beside an Eastern digit.
        return parts.isEmpty ? "—" : parts.joined(separator: "  ·  ")
    }

    /// A value as the log wrote it; null is no value.
    static func text(_ value: JSONValue) -> String? {
        switch value {
        case .null: nil
        case .string(let text): text
        case .int(let number): String(number)
        case .double(let number): String(number)
        case .bool(let flag): flag ? "true" : "false"
        case .array(let items): "[" + items.map { text($0) ?? "null" }.joined(separator: ", ") + "]"
        case .object(let fields):
            "{" + fields.keys.sorted().map { "\($0): \(fields[$0].flatMap(text) ?? "null")" }.joined(separator: ", ") + "}"
        }
    }
}

// MARK: - A row

private struct OpAuditRowView: View {
    @Environment(\.strings) private var strings
    let entry: AuditEntry

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                LTRText(entry.action)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
                StatusChip("\u{2066}\(entry.entityType)\u{2069}")
                Spacer(minLength: 0)
                DateText(entry.occurredAt, style: .relative)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            HStack(spacing: Spacing.s1) {
                OpAuditActor(entry: entry)
                DotSeparator().accessibilityHidden(true)
                Text(OpText.role(entry.actorRole, strings))
                DotSeparator().accessibilityHidden(true)
                DateText(entry.occurredAt)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
            .lineLimit(1)
            Text("\u{2066}\(OpAuditDiff.summary(entry))\u{2069}")
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(Palette.text)
                .lineLimit(2)
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("audit.row." + entry.action)
    }
}

/// Who did it: the name, or the id -- the id is not a name, but it is an
/// answer, and the one question the log exists to settle is which person.
private struct OpAuditActor: View {
    @Environment(\.strings) private var strings
    let entry: AuditEntry

    var body: some View {
        if let name = entry.actorName, !name.isEmpty {
            Text(name)
        } else if let id = entry.actorId {
            LTRText(id)
        } else {
            Text(strings["common.value.unknown"])
        }
    }
}

// MARK: - The detail

private struct OpAuditDetailView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let entry: AuditEntry
    let model: OpAuditModel

    var body: some View {
        Form {
            Section {
                OpDetailTitle(entry.action, isLatin: true) {
                    StatusChip("\u{2066}\(entry.entityType)\u{2069}")
                    StatusChip(OpText.role(entry.actorRole, strings))
                }
                .padding(.vertical, Spacing.s2)
            }
            Section {
                OpField("admin.col.when") {
                    VStack(alignment: .trailing, spacing: 2) {
                        DateText(entry.occurredAt)
                        DateText(entry.occurredAt, style: .relative)
                            .opsFont(.caption)
                            .foregroundStyle(Palette.textMuted)
                    }
                }
                OpField("admin.col.who") { OpAuditActor(entry: entry) }
                if let id = entry.actorId, entry.actorName != nil {
                    OpField("ops.audit.actor_id") { LTRText(id).opsFont(.caption) }
                }
                OpField("admin.col.entity") { LTRText(entry.entityType) }
                OpField("ops.audit.entity_id") { LTRText(entry.entityId).opsFont(.caption) }
                OpField("ops.audit.origin") { LTRText(entry.origin) }
            }
            Section {
                let changes = OpAuditDiff.changes(entry)
                if changes.isEmpty {
                    Text("—").foregroundStyle(Palette.textMuted)
                } else {
                    ForEach(changes) { change in
                        VStack(alignment: .leading, spacing: Spacing.s1) {
                            LTRText(change.field)
                                .opsFont(.label, weight: .medium)
                                .foregroundStyle(Palette.text)
                            HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
                                valueBox("ops.audit.before", change.before, tone: .failed)
                                Image(systemName: strings.locale.isRTL ? "arrow.left" : "arrow.right")
                                    .foregroundStyle(Palette.textMuted)
                                    .accessibilityHidden(true)
                                valueBox("ops.audit.after", change.after, tone: .active)
                            }
                        }
                        .padding(.vertical, 2)
                        .accessibilityElement(children: .combine)
                    }
                }
            } header: {
                OpFormHeader(titleKey: "admin.col.change")
            }
            Section {
                Button {
                    filter(\.action, entry.action)
                } label: {
                    Label(strings["ops.audit.filter_to", ["value": "\u{2066}\(entry.action)\u{2069}"]],
                          systemImage: "line.3.horizontal.decrease")
                }
                Button {
                    filter(\.entityType, entry.entityType)
                } label: {
                    Label(strings["ops.audit.filter_to", ["value": "\u{2066}\(entry.entityType)\u{2069}"]],
                          systemImage: "line.3.horizontal.decrease")
                }
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background)
        .opNavigationTitle(entry.action)
    }

    private func valueBox(_ labelKey: String, _ value: String?, tone: StatusTone) -> some View {
        let colors = Palette.chip(tone)
        return VStack(alignment: .leading, spacing: 2) {
            Text(strings[labelKey])
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
            Text("\u{2066}\(value ?? "—")\u{2069}")
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(value == nil ? Palette.textMuted : colors.foreground)
                .textSelection(.enabled)
        }
        .padding(Spacing.s2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(value == nil ? Palette.surfaceMuted : colors.background,
                    in: RoundedRectangle(cornerRadius: Radius.sm, style: .continuous))
    }

    private func filter(_ key: ReferenceWritableKeyPath<OpAuditModel, String?>, _ value: String) {
        model.action = nil
        model.entityType = nil
        model[keyPath: key] = value
        Task { [model, ops] in await model.reload(ops) }
    }
}
