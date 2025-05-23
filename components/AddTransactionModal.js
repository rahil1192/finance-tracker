"use client"

import { useState, useEffect } from "react"
import { View, Text, StyleSheet, TouchableOpacity, TextInput, ScrollView, Switch } from "react-native"
import { Ionicons } from "@expo/vector-icons"
import { useNavigation, useRoute } from "@react-navigation/native"

export default function AddTransactionModal() {
  const navigation = useNavigation()
  const route = useRoute()
  const initialTab = route.params?.initialTab || "EXPENSE"
  const existingTransaction = route.params?.transaction || null

  const [activeTab, setActiveTab] = useState(initialTab)
  const [amount, setAmount] = useState("")
  const [category, setCategory] = useState("Misc Expenses")
  const [merchant, setMerchant] = useState("Rogers")
  const [account, setAccount] = useState("Select Account")
  const [date, setDate] = useState(new Date())
  const [notes, setNotes] = useState("")
  const [fromAccount, setFromAccount] = useState("")
  const [toAccount, setToAccount] = useState("")
  const [title, setTitle] = useState("")
  const [repeatOption, setRepeatOption] = useState("Select repeat option")
  const [reminderDays, setReminderDays] = useState("Remind 5 days before")
  const [isAutoPaid, setIsAutoPaid] = useState(false)
  const [addExpenseEntry, setAddExpenseEntry] = useState(true)

  // Load transaction data if editing an existing transaction
  useEffect(() => {
    if (existingTransaction) {
      setActiveTab(existingTransaction.type || "EXPENSE")
      setAmount(Math.abs(existingTransaction.amount).toString())
      setCategory(existingTransaction.category || "Misc Expenses")
      setMerchant(existingTransaction.name || "Rogers")
      setNotes(existingTransaction.notes || "")

      if (typeof existingTransaction.date === "string") {
        try {
          setDate(new Date(existingTransaction.date))
        } catch (e) {
          console.error("Error parsing date:", e)
          setDate(new Date())
        }
      } else {
        setDate(new Date())
      }
    }
  }, [existingTransaction])

  const handleClose = () => {
    navigation.goBack()
  }

  const handleSave = () => {
    const transactionData = {
      id: existingTransaction ? existingTransaction.id : Date.now().toString(),
      name: activeTab === "BILLS" ? title : merchant,
      amount: activeTab === "EXPENSE" ? -Math.abs(Number.parseFloat(amount)) : Number.parseFloat(amount),
      category: category,
      date: date.toISOString(),
      notes: notes,
      fromAccount: activeTab === "TRANSFER" ? fromAccount : "",
      toAccount: activeTab === "TRANSFER" ? toAccount : "",
      type: activeTab,
      // Bill specific fields
      repeatOption: activeTab === "BILLS" ? repeatOption : "",
      reminderDays: activeTab === "BILLS" ? reminderDays : "",
      isAutoPaid: activeTab === "BILLS" ? isAutoPaid : false,
      addExpenseEntry: activeTab === "BILLS" ? addExpenseEntry : false,
    }

    console.log("Saving transaction:", transactionData)
    navigation.goBack()
  }

  const formatDate = (date) => {
    return date.toLocaleString("en-US", {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    })
  }

  // Expense Tab Content
  const ExpenseTabContent = () => (
    <ScrollView style={styles.content}>
      {/* Amount */}
      <View style={styles.amountContainer}>
        <View style={styles.iconContainer}>
          <Ionicons name="logo-usd" size={20} color="white" />
        </View>
        <TextInput
          style={styles.amountInput}
          value={amount}
          onChangeText={setAmount}
          keyboardType="decimal-pad"
          placeholder="0"
          placeholderTextColor="#64748b"
        />
        <View style={styles.amountActions}>
          <TouchableOpacity style={styles.actionButton}>
            <Ionicons name="arrow-forward" size={16} color="white" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionButton}>
            <Ionicons name="calculator" size={16} color="white" />
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.divider} />

      {/* Category */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#e11d48" }]}>
          <Ionicons name="receipt" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{category}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Merchant/Name */}
      <View style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#dc2626" }]}>
          <Ionicons name="business" size={20} color="white" />
        </View>
        <TextInput
          style={styles.rowTextInput}
          value={merchant}
          onChangeText={setMerchant}
          placeholder="Merchant name"
          placeholderTextColor="#64748b"
        />
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </View>

      <View style={styles.divider} />

      {/* Account Selection */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="card" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{account}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Date */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="calendar" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{formatDate(date)}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Notes */}
      <View style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="list" size={20} color="white" />
        </View>
        <TextInput
          style={styles.rowTextInput}
          value={notes}
          onChangeText={setNotes}
          placeholder="Notes..."
          placeholderTextColor="#64748b"
        />
      </View>

      <View style={styles.largeDivider} />

      {/* Attach Photo */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="camera" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>Attach photo</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* More */}
      <TouchableOpacity style={styles.moreButton}>
        <Text style={styles.moreText}>More</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>
    </ScrollView>
  )

  // Income Tab Content
  const IncomeTabContent = () => (
    <ScrollView style={styles.content}>
      {/* Amount */}
      <View style={styles.amountContainer}>
        <View style={styles.iconContainer}>
          <Ionicons name="logo-usd" size={20} color="white" />
        </View>
        <TextInput
          style={styles.amountInput}
          value={amount}
          onChangeText={setAmount}
          keyboardType="decimal-pad"
          placeholder="0"
          placeholderTextColor="#64748b"
        />
        <View style={styles.amountActions}>
          <TouchableOpacity style={styles.actionButton}>
            <Ionicons name="arrow-forward" size={16} color="white" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionButton}>
            <Ionicons name="calculator" size={16} color="white" />
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.divider} />

      {/* Income Source */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#22c55e" }]}>
          <Ionicons name="cash" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{category}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Payer */}
      <View style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#16a34a" }]}>
          <Ionicons name="person" size={20} color="white" />
        </View>
        <TextInput
          style={styles.rowTextInput}
          value={merchant}
          onChangeText={setMerchant}
          placeholder="Payer name"
          placeholderTextColor="#64748b"
        />
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </View>

      <View style={styles.divider} />

      {/* Account Selection */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="card" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{account}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Date */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="calendar" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{formatDate(date)}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Notes */}
      <View style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="list" size={20} color="white" />
        </View>
        <TextInput
          style={styles.rowTextInput}
          value={notes}
          onChangeText={setNotes}
          placeholder="Notes..."
          placeholderTextColor="#64748b"
        />
      </View>

      <View style={styles.largeDivider} />

      {/* Attach Photo */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="camera" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>Attach photo</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* More */}
      <TouchableOpacity style={styles.moreButton}>
        <Text style={styles.moreText}>More</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>
    </ScrollView>
  )

  // Transfer Tab Content
  const TransferTabContent = () => (
    <ScrollView style={styles.content}>
      <View style={styles.simpleForm}>
        {/* Amount Input */}
        <View style={styles.simpleInputGroup}>
          <Text style={styles.simpleLabel}>Amount</Text>
          <TextInput
            style={styles.simpleInput}
            value={amount}
            onChangeText={setAmount}
            keyboardType="decimal-pad"
            placeholder="0.00"
            placeholderTextColor="#64748b"
          />
        </View>

        {/* From Account */}
        <View style={styles.simpleInputGroup}>
          <Text style={styles.simpleLabel}>From Account</Text>
          <TextInput
            style={styles.simpleInput}
            value={fromAccount}
            onChangeText={setFromAccount}
            placeholder="Select account"
            placeholderTextColor="#64748b"
          />
        </View>

        {/* To Account */}
        <View style={styles.simpleInputGroup}>
          <Text style={styles.simpleLabel}>To Account</Text>
          <TextInput
            style={styles.simpleInput}
            value={toAccount}
            onChangeText={setToAccount}
            placeholder="Select account"
            placeholderTextColor="#64748b"
          />
        </View>

        {/* Description */}
        <View style={styles.simpleInputGroup}>
          <Text style={styles.simpleLabel}>Description</Text>
          <TextInput
            style={styles.simpleInput}
            value={merchant}
            onChangeText={setMerchant}
            placeholder="Enter description"
            placeholderTextColor="#64748b"
          />
        </View>

        {/* Notes */}
        <View style={styles.simpleInputGroup}>
          <Text style={styles.simpleLabel}>Notes</Text>
          <TextInput
            style={styles.simpleInput}
            value={notes}
            onChangeText={setNotes}
            placeholder="Add notes"
            placeholderTextColor="#64748b"
            multiline
          />
        </View>
      </View>
    </ScrollView>
  )

  // Bills Tab Content
  const BillsTabContent = () => (
    <ScrollView style={styles.content}>
      {/* Amount Due */}
      <View style={styles.row}>
        <View style={styles.rowIcon}>
          <Ionicons name="logo-usd" size={20} color="white" />
        </View>
        <TextInput
          style={[styles.rowTextInput, styles.amountDueInput]}
          value={amount}
          onChangeText={setAmount}
          keyboardType="decimal-pad"
          placeholder="Amount due"
          placeholderTextColor="#64748b"
        />
      </View>

      <View style={styles.divider} />

      {/* Category */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="list" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>Select category</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Title */}
      <View style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="document-text" size={20} color="white" />
        </View>
        <TextInput
          style={styles.rowTextInput}
          value={title}
          onChangeText={setTitle}
          placeholder="Title..."
          placeholderTextColor="#64748b"
        />
      </View>

      <View style={styles.divider} />

      {/* Due Date */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="calendar" size={20} color="white" />
        </View>
        <View style={styles.dateContainer}>
          <Text style={styles.rowText}>{formatDate(date)}</Text>
          <Text style={styles.subText}>Due Date</Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Repeat Option */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="refresh" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{repeatOption}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Reminder */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="notifications" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>{reminderDays}</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.largeDivider} />

      {/* Auto Paid */}
      <View style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="checkbox" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>Auto Paid</Text>
        <Switch
          value={isAutoPaid}
          onValueChange={setIsAutoPaid}
          trackColor={{ false: "#374151", true: "#0ea5e9" }}
          thumbColor={isAutoPaid ? "#ffffff" : "#f4f3f4"}
        />
      </View>

      {isAutoPaid && (
        <View style={styles.noteContainer}>
          <Text style={styles.noteText}>Note: Auto-paid bills are marked as paid on the due date in the app.</Text>
        </View>
      )}

      <View style={styles.divider} />

      {/* From Account */}
      <TouchableOpacity style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="card" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>From account</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>

      <View style={styles.divider} />

      {/* Add Expense Entry */}
      <View style={styles.row}>
        <Text style={styles.rowText}>Add expense entry for this payment.</Text>
        <Switch
          value={addExpenseEntry}
          onValueChange={setAddExpenseEntry}
          trackColor={{ false: "#374151", true: "#0ea5e9" }}
          thumbColor={addExpenseEntry ? "#ffffff" : "#f4f3f4"}
        />
      </View>

      <View style={styles.largeDivider} />

      {/* Notes */}
      <View style={styles.row}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="list" size={20} color="white" />
        </View>
        <TextInput
          style={styles.rowTextInput}
          value={notes}
          onChangeText={setNotes}
          placeholder="Notes..."
          placeholderTextColor="#64748b"
        />
      </View>

      <View style={styles.divider} />

      {/* Attach Photo */}
      <TouchableOpacity style={[styles.row, styles.attachPhotoRow]}>
        <View style={[styles.rowIcon, { backgroundColor: "#64748b" }]}>
          <Ionicons name="camera" size={20} color="white" />
        </View>
        <Text style={styles.rowText}>Attach photo</Text>
        <Ionicons name="chevron-forward" size={16} color="#64748b" />
      </TouchableOpacity>
    </ScrollView>
  )

  // Render the appropriate tab content based on activeTab
  const renderTabContent = () => {
    switch (activeTab) {
      case "EXPENSE":
        return <ExpenseTabContent />
      case "INCOME":
        return <IncomeTabContent />
      case "TRANSFER":
        return <TransferTabContent />
      case "BILLS":
        return <BillsTabContent />
      default:
        return <ExpenseTabContent />
    }
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={handleClose}>
          <Ionicons name="arrow-back" size={24} color="white" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {existingTransaction ? `Edit ${activeTab}` : activeTab === "BILLS" ? "Add Bill" : `Add ${activeTab}`}
        </Text>
        <TouchableOpacity onPress={handleSave}>
          <Ionicons name="checkmark" size={24} color="#0ea5e9" />
        </TouchableOpacity>
      </View>

      {/* Tabs */}
      <View style={styles.tabContainer}>
        {["EXPENSE", "INCOME", "TRANSFER", "BILLS"].map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[styles.tab, activeTab === tab && styles.activeTab]}
            onPress={() => setActiveTab(tab)}
          >
            <Text style={[styles.tabText, activeTab === tab && styles.activeTabText]}>{tab}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Content - Render the appropriate tab content */}
      {renderTabContent()}
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0f172a",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: "#1e40af",
    paddingTop: 50,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: "bold",
    color: "white",
  },
  tabContainer: {
    flexDirection: "row",
    backgroundColor: "#1e293b",
  },
  tab: {
    flex: 1,
    paddingVertical: 16,
    alignItems: "center",
  },
  activeTab: {
    borderBottomWidth: 2,
    borderBottomColor: "#0ea5e9",
  },
  tabText: {
    fontSize: 14,
    fontWeight: "500",
    color: "#94a3b8",
  },
  activeTabText: {
    color: "#0ea5e9",
  },
  content: {
    flex: 1,
    backgroundColor: "#0f172a",
  },
  amountContainer: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "#64748b",
    justifyContent: "center",
    alignItems: "center",
    marginRight: 12,
  },
  amountInput: {
    flex: 1,
    fontSize: 36,
    fontWeight: "bold",
    color: "white",
    padding: 0,
  },
  amountDueInput: {
    fontSize: 24,
    fontWeight: "bold",
  },
  amountActions: {
    flexDirection: "row",
    gap: 6,
  },
  actionButton: {
    width: 32,
    height: 32,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "#374151",
    justifyContent: "center",
    alignItems: "center",
  },
  divider: {
    height: 1,
    backgroundColor: "#374151",
    marginHorizontal: 16,
  },
  largeDivider: {
    height: 8,
    backgroundColor: "#374151",
    marginVertical: 16,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  rowIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "#64748b",
    justifyContent: "center",
    alignItems: "center",
    marginRight: 12,
  },
  rowText: {
    flex: 1,
    fontSize: 16,
    color: "white",
  },
  rowTextInput: {
    flex: 1,
    fontSize: 16,
    color: "white",
    padding: 0,
  },
  dateContainer: {
    flex: 1,
  },
  subText: {
    fontSize: 12,
    color: "#64748b",
    marginTop: 2,
  },
  moreButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: "#1e293b",
    marginHorizontal: 16,
    borderRadius: 12,
    marginBottom: 20,
  },
  moreText: {
    fontSize: 16,
    color: "white",
  },
  // Styles for simple form
  simpleForm: {
    padding: 16,
  },
  simpleInputGroup: {
    marginBottom: 16,
  },
  simpleLabel: {
    fontSize: 14,
    color: "#94a3b8",
    marginBottom: 8,
  },
  simpleInput: {
    borderBottomWidth: 1,
    borderBottomColor: "#374151",
    paddingBottom: 8,
    fontSize: 16,
    color: "white",
  },
  noteContainer: {
    backgroundColor: "#7c2d12",
    marginHorizontal: 16,
    marginTop: 4,
    marginBottom: 8,
    padding: 12,
    borderRadius: 8,
  },
  noteText: {
    color: "white",
    fontSize: 14,
  },
  attachPhotoRow: {
    marginBottom: 20,
  },
})
