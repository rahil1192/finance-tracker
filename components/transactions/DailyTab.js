"use client"

import { useState, useEffect } from "react"
import { View, Text, StyleSheet, TouchableOpacity, FlatList, ActivityIndicator } from "react-native"
import { Ionicons } from "@expo/vector-icons"
import { useNavigation } from "@react-navigation/native"
import axios from "axios"

export default function DailyTab() {
  const navigation = useNavigation()
  const [activeFilter, setActiveFilter] = useState("All")
  const [transactions, setTransactions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchTransactions()
  }, [])

  const fetchTransactions = async () => {
    try {
      setLoading(true)
      const response = await axios.get("http://192.168.2.19:8001/api/transactions")

      // Validate response data
      if (!response.data || !Array.isArray(response.data)) {
        console.error("Invalid response format:", response.data)
        throw new Error("Invalid response format from server")
      }

      // Group transactions by date
      const groupedTransactions = response.data.reduce((groups, transaction) => {
        // Validate transaction object
        if (!transaction || !transaction.date || !transaction.amount) {
          console.warn("Invalid transaction object:", transaction)
          return groups
        }

        const date = new Date(transaction.date).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        })

        if (!groups[date]) {
          groups[date] = {
            date,
            total: 0,
            transactions: [],
          }
        }

        // Convert amount based on transaction type
        const amount =
          transaction.transaction_type === "Debit" ? -Math.abs(transaction.amount) : Math.abs(transaction.amount)

        groups[date].transactions.push({
          id: transaction.id,
          name: transaction.details,
          icon: getTransactionIcon(transaction.category),
          iconBgColor: getCategoryColor(transaction.category),
          amount: amount,
          category: transaction.category,
          date: date,
          bank: transaction.bank,
          statementType: transaction.statement_type,
          // Add full transaction data for modal
          fullDate: transaction.date,
          notes: transaction.details,
          transactionType: transaction.transaction_type,
        })

        groups[date].total += amount

        return groups
      }, {})

      // Convert grouped transactions to array and sort by date
      const sortedTransactions = Object.values(groupedTransactions).sort((a, b) => new Date(b.date) - new Date(a.date))

      setTransactions(sortedTransactions)
      setError(null)
    } catch (err) {
      console.error("Error details:", err)
      setError(err.message || "Failed to fetch transactions")
    } finally {
      setLoading(false)
    }
  }

  const getTransactionIcon = (category) => {
    const iconMap = {
      Transfers: "swap-horizontal-outline",
      Food: "restaurant-outline",
      Transportation: "car-outline",
      Shopping: "cart-outline",
      Bills: "document-text-outline",
      Entertainment: "game-controller-outline",
      Health: "fitness-outline",
      Income: "cash-outline",
      default: "card-outline",
    }
    return iconMap[category] || iconMap.default
  }

  const getCategoryColor = (category) => {
    const colorMap = {
      Transfers: "#8b5cf6",
      Food: "#e11d48",
      Transportation: "#0ea5e9",
      Shopping: "#8b5cf6",
      Bills: "#f59e0b",
      Entertainment: "#ec4899",
      Health: "#10b981",
      Income: "#22c55e",
      default: "#64748b",
    }
    return colorMap[category] || colorMap.default
  }

  const handleTransactionPress = (transaction) => {
    // Determine the transaction type for the modal tab
    let transactionType = "Expense"

    if (transaction.category === "Income" || transaction.amount > 0) {
      transactionType = "Income"
    } else if (transaction.category === "Transfers") {
      transactionType = "Transfer"
    }

    // Open the AddTransactionModal with the appropriate tab
    navigation.navigate("AddTransaction", {
      initialTab: transactionType,
      transaction: {
        id: transaction.id,
        name: transaction.name,
        amount: Math.abs(transaction.amount),
        category: transaction.category,
        date: transaction.fullDate,
        notes: transaction.notes,
        icon: transaction.icon,
        iconBgColor: transaction.iconBgColor,
        bank: transaction.bank,
        type: transactionType,
      },
    })
  }

  const filterTransactions = (data) => {
    if (activeFilter === "All") return data

    return data
      .map((group) => {
        const filteredTransactions = group.transactions.filter((transaction) => {
          if (activeFilter === "Expenses") return transaction.amount < 0
          if (activeFilter === "Income") return transaction.amount > 0
          return true
        })

        const newTotal = filteredTransactions.reduce((sum, transaction) => sum + transaction.amount, 0)

        return {
          ...group,
          transactions: filteredTransactions,
          total: newTotal,
        }
      })
      .filter((group) => group.transactions.length > 0)
  }

  const renderTransactionItem = ({ item }) => {
    // Get first three words of the transaction name
    const shortName = item.name.split(" ").slice(0, 5).join(" ")

    return (
      <TouchableOpacity style={styles.transactionItem} onPress={() => handleTransactionPress(item)}>
        <View style={[styles.iconContainer, { backgroundColor: item.iconBgColor }]}>
          <Ionicons name={item.icon} size={24} color="white" />
        </View>
        <View style={styles.transactionInfo}>
          <Text style={styles.transactionName}>{item.category}</Text>
          <Text style={styles.transactionMeta}>
            {item.bank}.{shortName}
          </Text>
        </View>
        <Text style={[styles.transactionAmount, { color: item.amount > 0 ? "#22c55e" : "white" }]}>
          {item.amount > 0 ? "+" : "-"} ${Math.abs(item.amount).toFixed(2)}
        </Text>
        <View style={[styles.transactionIndicator, { backgroundColor: item.amount > 0 ? "#22c55e" : "#f59e0b" }]} />
      </TouchableOpacity>
    )
  }

  const renderDateGroup = ({ item }) => (
    <View style={styles.dateGroup}>
      <View style={styles.dateHeader}>
        <Text style={styles.dateText}>{item.date}</Text>
        <Text style={[styles.dateTotalAmount, { color: item.total > 0 ? "#22c55e" : "white" }]}>
          {item.total > 0 ? "+" : "-"} ${Math.abs(item.total).toFixed(2)}
        </Text>
      </View>
      <FlatList
        data={item.transactions}
        renderItem={renderTransactionItem}
        keyExtractor={(item) => item.id.toString()}
        scrollEnabled={false}
      />
    </View>
  )

  const filteredData = filterTransactions(transactions)

  if (loading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#0ea5e9" />
      </View>
    )
  }

  if (error) {
    return (
      <View style={styles.errorContainer}>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryButton} onPress={fetchTransactions}>
          <Text style={styles.retryButtonText}>Retry</Text>
        </TouchableOpacity>
      </View>
    )
  }

  return (
    <View style={styles.container}>
      {/* Filters */}
      <View style={styles.filterContainer}>
        {["All", "Expenses", "Income"].map((filter) => (
          <TouchableOpacity
            key={filter}
            style={[styles.filterButton, activeFilter === filter && styles.activeFilterButton]}
            onPress={() => setActiveFilter(filter)}
          >
            <Text style={[styles.filterText, activeFilter === filter && styles.activeFilterText]}>{filter}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Transactions List */}
      <FlatList
        data={filteredData}
        renderItem={renderDateGroup}
        keyExtractor={(item) => item.date}
        style={styles.transactionsList}
        refreshing={loading}
        onRefresh={fetchTransactions}
      />
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0f172a",
  },
  loadingContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#0f172a",
  },
  errorContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#0f172a",
    padding: 20,
  },
  errorText: {
    color: "#ef4444",
    fontSize: 16,
    marginBottom: 16,
    textAlign: "center",
  },
  retryButton: {
    backgroundColor: "#0ea5e9",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  retryButtonText: {
    color: "white",
    fontSize: 16,
    fontWeight: "500",
  },
  filterContainer: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 16,
    backgroundColor: "#0f172a",
  },
  filterButton: {
    flex: 1,
    paddingVertical: 8,
    paddingHorizontal: 8,
    borderRadius: 16,
    marginHorizontal: 2,
    backgroundColor: "#1e293b",
    alignItems: "center",
    justifyContent: "center",
  },
  activeFilterButton: {
    backgroundColor: "#0c4a6e",
  },
  filterText: {
    fontSize: 14,
    color: "#94a3b8",
    fontWeight: "500",
  },
  activeFilterText: {
    color: "#0ea5e9",
  },
  transactionsList: {
    flex: 1,
  },
  dateGroup: {
    marginBottom: 16,
  },
  dateHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  dateText: {
    fontSize: 18,
    fontWeight: "bold",
    color: "white",
  },
  dateTotalAmount: {
    fontSize: 18,
    fontWeight: "bold",
    color: "white",
  },
  transactionItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 16,
    paddingHorizontal: 16,
    backgroundColor: "#1e293b",
    marginHorizontal: 16,
    borderRadius: 12,
    marginBottom: 8,
    position: "relative",
    overflow: "hidden",
  },
  iconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: "center",
    alignItems: "center",
    marginRight: 16,
  },
  transactionInfo: {
    flex: 1,
  },
  transactionName: {
    fontSize: 16,
    fontWeight: "bold",
    color: "white",
    marginBottom: 4,
  },
  transactionMeta: {
    fontSize: 14,
    color: "#94a3b8",
  },
  transactionAmount: {
    fontSize: 16,
    fontWeight: "bold",
    color: "white",
    marginLeft: 8,
  },
  transactionIndicator: {
    position: "absolute",
    right: 0,
    top: 0,
    bottom: 0,
    width: 6,
    backgroundColor: "#f59e0b",
  },
})
